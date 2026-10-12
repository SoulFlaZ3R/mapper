import json
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from PySide6.QtCore import QCoreApplication, QUrl
from backend import MapperBackend
from scanner import scan_folder

APP = QCoreApplication.instance() or QCoreApplication([])


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
        return [row['itemName'] for row in self.backend.model.rows]

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
        self.assertEqual(self.backend.model.rows[revealed[0]]['itemName'], 'target.md')
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
        expected = scan_folder(str(self.root))
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


if __name__ == '__main__':
    unittest.main()
