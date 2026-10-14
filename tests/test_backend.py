import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from PySide6.QtCore import QCoreApplication, QUrl
from unittest import mock
from backend import MapperBackend, UserError, config_location
import reference_scanner_v15 as legacy  # mappa della 1.5 / 1.5 map

APP = QCoreApplication.instance() or QCoreApplication([])
BS = chr(92)


def junction(link, target):
    subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)], check=True, capture_output=True)


def unlink_junctions(top):
    """Rimuove solo i collegamenti, mai il loro contenuto / Removes only links, never their content."""
    for dirpath, dirnames, _ in os.walk(BS * 2 + '?' + BS + str(top)):
        for name in list(dirnames):
            path = os.path.join(dirpath, name)
            if os.path.isjunction(path) or os.path.islink(path):
                os.rmdir(path)
                dirnames.remove(name)


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        # Forma completa del percorso, come nell'app (su GitHub TEMP è RUNNER~1)
        # Full path form, as in the app (on GitHub TEMP is RUNNER~1)
        self.root = Path(self.temp.name).resolve() / 'root'
        self.root.mkdir()
        (self.root / 'nested').mkdir()
        (self.root / 'nested' / 'report.TXT').write_text('report')
        (self.root / 'photo.png').write_text('image')
        (self.root / 'desktop.ini').touch()
        config = Path(self.temp.name) / 'config.json'
        config.write_text(json.dumps(dict(language='en')), encoding='utf-8')
        self.backend = MapperBackend(config)
        # Il Cestino reale non va toccato dai test / Tests never touch the real Recycle Bin
        self.trashed = []
        def fake_trash(path):
            self.trashed.append(Path(path).name)
            shutil.rmtree(path) if Path(path).is_dir() else Path(path).unlink()
        self.backend._trash = fake_trash
        self.resets = 0
        self.backend.model.modelReset.connect(self.count_reset)
        self.backend.setPath(str(self.root))

    def count_reset(self):
        self.resets += 1

    def tearDown(self):
        self.wait(lambda: not self.backend.state['busy'])
        self.backend.shutdown()
        unlink_junctions(self.temp.name)
        shutil.rmtree(BS * 2 + '?' + BS + str(Path(self.temp.name).resolve()), ignore_errors=True)
        self.temp.cleanup()

    def wait(self, predicate):
        deadline = time.monotonic() + 10
        while not predicate() and time.monotonic() < deadline:
            APP.processEvents()
            time.sleep(0.005)
        self.assertTrue(predicate(), self.backend.state)

    def settle(self):
        self.wait(lambda: not self.backend.state['busy'])
        deadline = time.monotonic() + 0.3
        while time.monotonic() < deadline:
            APP.processEvents()
            time.sleep(0.005)

    def scan(self):
        self.backend.scan()
        self.wait(lambda: not self.backend.state['busy'])
        self.wait(lambda: self.backend.model.rowCount() > 0)

    def names(self):
        model = self.backend.model
        return [model.item(row)['itemName'] for row in range(model.rowCount())]

    def act(self, action, path, name=''):
        self.backend.fileAction(action, str(path), name)
        self.settle()

    def test_expansion_is_incremental_and_search_is_recursive(self):
        self.scan()
        self.assertEqual(self.names(), ['nested', 'photo.png'])
        resets, updated, model = self.resets, [], self.backend.model
        model.dataChanged.connect(lambda first, last: updated.append((first.row(), last.row())))
        self.backend.toggle(str(self.root / 'nested'))
        self.wait(lambda: model.rowCount() == 3)
        self.assertEqual(self.resets, resets, 'expanding must insert rows, not reset the view')
        self.assertEqual(updated, [(0, 0)], 'the toggled folder row must be refreshed in the view')
        role = next(r for r, name in model.roleNames().items() if name == b'expanded')
        self.assertTrue(model.data(model.index(0), role))
        self.backend.toggle(str(self.root / 'nested'))
        self.wait(lambda: model.rowCount() == 2)
        self.assertEqual(updated, [(0, 0), (0, 0)])
        self.backend.setQuery('REPORT')
        self.wait(lambda: self.names() == ['report.TXT'])
        self.backend.setQuery('')
        self.backend.setExtension('.png')
        self.wait(lambda: self.names() == ['photo.png'])
        self.assertEqual(self.backend.state['shown'], 1)
        self.backend.setExtension('.png')
        self.wait(lambda: self.names() == ['nested', 'photo.png'])

    def test_reveal_opens_ancestors_and_clears_search(self):
        (self.root / 'nested' / 'deeper').mkdir()
        (self.root / 'nested' / 'deeper' / 'target.md').touch()
        self.scan()
        revealed = []
        self.backend.revealed.connect(revealed.append)
        self.backend.setQuery('target')
        self.wait(lambda: self.names() == ['target.md'])
        self.backend.reveal(str(self.root / 'nested' / 'deeper' / 'target.md'))
        self.wait(lambda: revealed)
        self.assertEqual(self.backend.state['query'], '')
        self.assertEqual(self.backend.model.item(revealed[0])['itemName'], 'target.md')
        self.assertEqual(self.names(), ['nested', 'deeper', 'target.md', 'report.TXT', 'photo.png'])

    def test_expand_all_and_collapse_all(self):
        self.scan()
        self.backend.expandAll(True)
        self.wait(lambda: self.backend.model.rowCount() == 3)
        self.backend.expandAll(False)
        self.wait(lambda: self.backend.model.rowCount() == 2)

    def test_export_matches_preview_and_reports_errors(self):
        self.scan()
        destination = Path(self.temp.name) / 'map.txt'
        self.backend.exportMap(QUrl.fromLocalFile(str(destination)).toString())
        self.settle()
        expected = legacy.scan_folder(str(self.root))
        self.assertEqual(destination.read_text(encoding='utf-8'), '\n'.join(expected) + '\n')
        self.assertEqual(self.backend.preview(), '\n'.join(expected))
        self.assertEqual(self.backend.lineCount(), len(expected))
        self.backend.exportMap(str(Path(self.temp.name) / 'missing' / 'map.txt'))
        self.settle()
        self.assertTrue(self.backend.state['error'])
        self.assertTrue(self.backend.state['status'].startswith('Operation failed'))

    def test_mutations_keep_open_folders_and_use_the_recycle_bin(self):
        self.scan()
        self.backend.toggle(str(self.root / 'nested'))
        self.wait(lambda: self.backend.model.rowCount() == 3)
        self.act('new_folder', self.root, 'created')
        self.assertTrue((self.root / 'created').is_dir())
        self.assertEqual(self.backend.state['folders'], 2)
        self.wait(lambda: 'report.TXT' in self.names())
        self.act('rename', self.root / 'photo.png', 'image.png')
        self.assertTrue((self.root / 'image.png').exists())
        self.backend.clipboard(str(self.root / 'image.png'), 'copy')
        self.act('paste', self.root / 'created')
        self.assertTrue((self.root / 'created' / 'image.png').exists())
        self.act('paste', self.root / 'created')
        self.assertTrue((self.root / 'created' / 'image - copy.png').exists())
        self.act('paste', self.root / 'created')
        self.assertTrue((self.root / 'created' / 'image - copy (2).png').exists())
        self.act('delete', self.root / 'created')
        self.assertFalse((self.root / 'created').exists())
        self.assertEqual(self.trashed, ['created'])
        self.assertIn('report.TXT', self.names())

    def test_case_only_rename_and_folder_clone(self):
        (self.root / 'v1.2').mkdir()
        self.scan()
        self.act('rename', self.root / 'photo.png', 'Photo.png')
        self.assertFalse(self.backend.state['error'], self.backend.state['status'])
        self.assertIn('Photo.png', [p.name for p in self.root.iterdir()])
        self.act('clone', self.root / 'v1.2')
        self.assertTrue((self.root / 'v1.2 - copy').is_dir())

    def test_cut_paste_moves_and_refuses_overwrite(self):
        (self.root / 'other').mkdir()
        (self.root / 'other' / 'photo.png').touch()
        self.scan()
        self.backend.clipboard(str(self.root / 'photo.png'), 'cut')
        self.assertEqual(self.backend.state['clipboardMode'], 'cut')
        self.act('paste', self.root / 'other')
        self.assertTrue(self.backend.state['error'])
        self.assertTrue((self.root / 'photo.png').exists())
        self.act('paste', self.root / 'nested')
        self.assertTrue((self.root / 'nested' / 'photo.png').exists())
        self.assertFalse((self.root / 'photo.png').exists())
        self.assertEqual(self.backend.state['clipboard'], '')

    def test_folder_cannot_be_pasted_into_itself(self):
        self.scan()
        self.backend.clipboard(str(self.root / 'nested'), 'copy')
        self.act('paste', self.root / 'nested' / 'report.TXT')
        self.assertTrue(self.backend.state['error'])
        self.assertFalse((self.root / 'nested' / 'nested').exists())

    def test_path_and_name_validation(self):
        for invalid in ['..', '.', 'NUL.txt', 'CON', '../escape', 'name.', 'name ', 'a:b', '']:
            self.assertFalse(self.backend.isValidName(invalid), invalid)
        self.assertTrue(self.backend.isValidName('report (final).txt'))
        self.backend.fileAction('delete', str(Path(self.temp.name) / 'escape'), '')
        self.assertTrue(self.backend.state['error'])
        (Path(self.temp.name) / 'outside.txt').write_text('keep')
        self.backend.fileAction('delete', str(self.root / '..' / 'outside.txt'), '')
        self.assertTrue(self.backend.state['error'])
        self.assertTrue((Path(self.temp.name) / 'outside.txt').exists())
        self.backend.fileAction('delete', str(self.root), '')
        self.assertTrue(self.root.exists())
        self.assertTrue(self.backend.state['error'])
        self.assertEqual(self.trashed, [])

    def test_preferences_recent_and_status_translation(self):
        self.scan()
        self.assertEqual(self.backend.recent, [str(self.root)])
        self.backend.preferences('dark', 'it', True)
        saved = json.loads(self.backend.config_path.read_text(encoding='utf-8'))
        self.assertEqual(saved, dict(theme='dark', language='it', reducedMotion=True, recent=[str(self.root)]))
        self.assertEqual(self.backend.translations['browse'], 'Sfoglia')
        self.assertTrue(self.backend.state['status'].startswith('Mappatura completata'))
        self.backend.previewPreferences('red', 'de', False)
        self.assertEqual(self.backend.state['theme'], 'red')
        self.assertEqual(json.loads(self.backend.config_path.read_text(encoding='utf-8'))['theme'], 'dark')
        restored = MapperBackend(self.backend.config_path)
        self.assertEqual((restored.state['theme'], restored.state['language'], restored.recent), ('dark', 'it', [str(self.root)]))
        restored.shutdown()

    def test_invalid_config_falls_back_to_defaults(self):
        self.backend.config_path.write_text('[1, 2]', encoding='utf-8')
        fallback = MapperBackend(self.backend.config_path)
        self.assertIn(fallback.state['theme'], ('light',))
        self.assertEqual(fallback.recent, [])
        fallback.shutdown()

    def test_cancel_does_not_publish_partial_snapshot(self):
        self.backend.scan()
        self.backend.cancel()
        self.settle()
        self.assertFalse(self.backend.state['scanned'])
        self.assertEqual(self.backend.model.rowCount(), 0)

    def test_new_path_clears_previous_results_and_open_folder_accepts_files(self):
        self.scan()
        self.backend.setQuery('photo')
        empty = Path(self.temp.name) / 'empty'
        empty.mkdir()
        self.backend.setPath(str(empty))
        self.assertFalse(self.backend.state['scanned'])
        self.assertEqual(self.backend.state['query'], '')
        self.backend.openFolder(QUrl.fromLocalFile(str(self.root / 'photo.png')).toString())
        self.settle()
        self.assertEqual(self.backend.state['path'], str(self.root))
        self.assertTrue(self.backend.state['scanned'])

    def test_wrong_path_keeps_the_current_map(self):
        self.scan()
        self.backend.openFolder(str(self.root / 'does-not-exist'))
        self.assertTrue(self.backend.state['error'])
        self.assertTrue(self.backend.state['scanned'])
        self.assertEqual(self.backend.state['path'], str(self.root))
        self.assertEqual(self.backend.model.rowCount(), 2)

    # ── Milestone 1A: sicurezza e robustezza / safety and robustness ──
    def capture_job(self, action, path, name=''):
        """Esegue fileAction trattenendo il job per lanciarlo dopo / Runs fileAction, keeping the job for later."""
        captured = []
        with mock.patch.object(self.backend, '_work', side_effect=lambda job, done, cancellable=True: captured.append(job)):
            self.backend.fileAction(action, str(path), name)
        self.assertEqual(len(captured), 1, self.backend.state['status'])
        return captured[0]

    def test_path_swapped_for_a_junction_after_the_click_is_refused(self):
        outside = Path(self.temp.name).resolve() / 'outside'
        outside.mkdir()
        (outside / 'precious.txt').write_text('keep')
        self.scan()
        job = self.capture_job('delete', self.root / 'nested')
        # Tra clic ed esecuzione la cartella diventa una junction verso l'esterno
        # Between click and execution the folder becomes a junction pointing outside
        os.rename(self.root / 'nested', self.root / 'nested-old')
        junction(self.root / 'nested', outside)
        with self.assertRaises(UserError) as raised:
            job(threading.Event())
        self.assertEqual(raised.exception.key, 'error_path_changed')
        self.assertEqual(self.trashed, [])
        self.assertTrue((outside / 'precious.txt').exists())

    def test_duplicate_folder_with_a_looping_junction_is_safe(self):
        junction(self.root / 'nested' / 'loop', self.root / 'nested')
        self.scan()
        self.act('clone', self.root / 'nested')
        self.assertFalse(self.backend.state['error'], self.backend.state['status'])
        copy = self.root / 'nested - copy'
        self.assertTrue(os.path.isjunction(copy / 'loop'))
        self.assertEqual(sorted(os.listdir(copy)), ['loop', 'report.TXT'])
        # La junction stessa punta alla sua cartella madre: duplicarla copierebbe la cartella in sé stessa
        # The junction points to its own parent: duplicating it would copy the folder into itself
        self.act('clone', self.root / 'nested' / 'loop')
        self.assertTrue(self.backend.state['error'])
        self.assertFalse((self.root / 'nested' / 'loop - copy').exists())

    def test_links_are_rows_of_kind_link(self):
        junction(self.root / 'shortcut', self.root / 'nested')
        self.scan()
        model = self.backend.model
        row = self.names().index('shortcut')
        item = model.item(row)
        self.assertEqual((item['kind'], item['directory'], item['extension']), ('link', False, ''))
        self.assertEqual(self.backend.state['links'], 1)

    def test_unreadable_folders_are_reported(self):
        locked = self.root / 'locked'
        locked.mkdir()
        user = os.environ['USERNAME']
        subprocess.run(['icacls', str(locked), '/deny', f'{user}:(OI)(CI)(RD)'], check=True, capture_output=True)
        try:
            self.scan()
        finally:
            subprocess.run(['icacls', str(locked), '/remove:d', user], check=True, capture_output=True)
        self.assertEqual(self.backend.state['errors'], 1)
        self.assertEqual(self.backend.scanErrors(), [dict(path=str(locked), reason='access_denied')])
        self.assertTrue(self.backend.state['status'].endswith('not readable: 1'), self.backend.state['status'])

    def test_actions_work_on_paths_longer_than_260_characters(self):
        deep = str(self.root)
        for i in range(9):
            deep += BS + f'segment_{i:02d}_' + 'x' * 24
        os.makedirs(BS * 2 + '?' + BS + deep)
        self.assertGreater(len(deep), 260)
        self.scan()
        self.act('new_folder', deep, 'made here')
        self.assertFalse(self.backend.state['error'], self.backend.state['status'])
        self.act('rename', deep + BS + 'made here', 'renamed')
        self.assertFalse(self.backend.state['error'], self.backend.state['status'])
        self.assertTrue(os.path.isdir(BS * 2 + '?' + BS + deep + BS + 'renamed'))
        self.assertGreaterEqual(self.backend._tree.index_of(deep + BS + 'renamed'), 0)


class ConfigLocationTests(unittest.TestCase):
    """Exe: preferenze in %APPDATA%/Mapper, accanto all'exe solo se config.json esiste già (chiavetta)."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name).resolve()
        self.desktop, self.appdata = base / 'Desktop', base / 'AppData'
        self.desktop.mkdir()
        self.patches = [mock.patch.object(sys, 'frozen', True, create=True),
                        mock.patch.object(sys, 'executable', str(self.desktop / 'Mapper.exe')),
                        mock.patch.dict('os.environ', {'APPDATA': str(self.appdata)})]
        for patch in self.patches:
            patch.start()

    def tearDown(self):
        for patch in reversed(self.patches):
            patch.stop()
        self.temp.cleanup()

    def test_exe_keeps_preferences_out_of_its_folder(self):
        location = config_location()
        self.assertEqual(location, self.appdata / 'Mapper' / 'config.json')
        backend = MapperBackend(location)
        backend.preferences('dark', 'en', False)
        backend.shutdown()
        self.assertTrue(location.is_file())
        self.assertEqual(list(self.desktop.iterdir()), [])

    def test_existing_config_next_to_exe_enables_usb_mode(self):
        (self.desktop / 'config.json').write_text('{}', encoding='utf-8')
        self.assertEqual(config_location(), self.desktop / 'config.json')


if __name__ == '__main__':
    unittest.main()
