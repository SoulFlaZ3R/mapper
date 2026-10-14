"""mapper_core: visita, modello dati, percorsi lunghi, errori, junction e copia sicura.
mapper_core: walk, data model, long paths, errors, junctions and safe copy."""
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import reference_scanner_v15 as legacy  # noqa: E402  scanner della 1.5, riferimento congelato / frozen 1.5 reference
from mapper_core import DIR, FILE, LINK, fsops, root_label, scan  # noqa: E402
from mapper_core.paths import display, extended  # noqa: E402


def junction(link, target):
    subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)], check=True, capture_output=True)


class TempTree(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / 'root'
        (self.root / 'nested').mkdir(parents=True)
        (self.root / 'nested' / 'report.TXT').write_text('report')
        (self.root / 'desktop.ini').write_text('ignored')
        (self.root / 'photo.png').write_text('image')
        (self.root / 'Alpha').mkdir()

    def tearDown(self):
        # Prima i collegamenti (solo il link), poi il resto / Links first (link only), then the rest
        for dirpath, dirnames, _ in os.walk(extended(str(self.base))):
            for name in list(dirnames):
                path = os.path.join(dirpath, name)
                if os.path.isjunction(path) or os.path.islink(path):
                    os.rmdir(path)
                    dirnames.remove(name)
        shutil.rmtree(extended(str(self.base)), ignore_errors=True)
        self.temp.cleanup()


class WalkerTests(TempTree):
    def test_lines_identical_to_1_5_and_counts(self):
        tree = scan(self.root)
        self.assertEqual(list(tree.lines()), legacy.scan_folder(str(self.root)))
        self.assertEqual(list(tree.lines()), ['root/', '├── Alpha/', '├── nested/', '│   └── report.TXT', '└── photo.png'])
        self.assertEqual((tree.folders, tree.files, tree.links, len(tree)), (2, 2, 0, 4))
        self.assertEqual(dict(tree.extensions), {'.txt': 1, '.png': 1})
        nested = tree.index_of(str(self.root / 'NESTED'))
        report = tree.index_of(str(self.root / 'nested' / 'report.txt'))
        self.assertEqual(tree.path(report), str(self.root / 'nested' / 'report.TXT'))
        self.assertEqual(tree.relative(report), os.path.join('nested', 'report.TXT'))
        self.assertEqual(tree.parent_path(report), str(self.root / 'nested'))
        self.assertEqual(tree.parents[report], nested)
        self.assertEqual([tree.names[i] for i in tree.children()], ['Alpha', 'nested', 'photo.png'])
        self.assertEqual(tree.index_of(str(self.root / 'missing')), -1)
        self.assertEqual(tree.index_of(str(self.base / 'rootless')), -1)

    def test_identical_to_1_5_on_a_larger_tree(self):
        for i in range(30):
            folder = self.root / f'd{i % 7}' / f'Sub {i % 3}' / ('ÀÉ' if i % 2 else 'zz')
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f'File {i}.{["md", "PY", "txt", ""][i % 4]}').write_text('x')
        self.assertEqual(list(scan(self.root).lines()), legacy.scan_folder(str(self.root)))

    def test_metadata_sizes_and_dates(self):
        (self.root / 'photo.png').write_bytes(b'x' * 1234)
        os.utime(self.root / 'photo.png', (1_600_000_000, 1_600_000_000))
        tree = scan(self.root)
        photo = tree.index_of(str(self.root / 'photo.png'))
        self.assertEqual(tree.size(photo), 1234)
        self.assertEqual(int(tree.mtime(photo)), 1_600_000_000)
        self.assertEqual(tree.size(tree.index_of(str(self.root / 'nested'))), -1)
        light = scan(self.root, metadata=False)
        self.assertEqual(light.size(0), -1)
        self.assertEqual(list(light.lines()), list(tree.lines()))

    def test_progress_and_cancel(self):
        seen = []
        tree = scan(self.root, progress=seen.append, progress_every=1)
        self.assertTrue(seen and seen[-1] <= len(tree))
        cancel = threading.Event()
        cancel.set()
        cancelled = scan(self.root, cancel=cancel)
        self.assertTrue(cancelled.cancelled)
        self.assertEqual(list(cancelled.lines()), ['root/'])

    def test_drive_root_label(self):
        self.assertEqual(root_label('D:\\'), 'D:/')
        self.assertEqual(root_label(str(self.root)), 'root/')

    def test_junctions_are_links_not_traversed(self):
        outside = self.base / 'outside'
        outside.mkdir()
        (outside / 'secret.txt').write_text('x')
        junction(self.root / 'loop', self.root)
        junction(self.root / 'out', outside)
        tree = scan(self.root)
        loop = tree.index_of(str(self.root / 'loop'))
        self.assertEqual(tree.kinds[loop], LINK)
        self.assertEqual(tree.links, 2)
        self.assertNotIn('secret.txt', tree.names)
        self.assertEqual(tree.extension(loop), '')
        # La mappa testuale resta quella della 1.5 / The text map stays the 1.5 one
        self.assertEqual(list(tree.lines()), legacy.scan_folder(str(self.root)))

    def test_long_paths_are_read(self):
        deep = str(self.root / 'long')
        for i in range(10):
            deep += '\\' + f'segment_{i:02d}_' + 'x' * 24
        os.makedirs(extended(deep))
        with open(extended(deep + '\\deep_file.txt'), 'w') as handle:
            handle.write('x')
        self.assertGreater(len(deep), 300)
        tree = scan(self.root)
        found = tree.index_of(deep + '\\deep_file.txt')
        self.assertGreaterEqual(found, 0)
        self.assertEqual(tree.path(found), deep + '\\deep_file.txt')
        self.assertEqual(tree.errors, [])

    def test_extended_and_display_forms(self):
        self.assertEqual(extended('C:\\a'), '\\\\?\\C:\\a')
        self.assertEqual(extended('\\\\server\\share\\x'), '\\\\?\\UNC\\server\\share\\x')
        self.assertEqual(display(extended('\\\\server\\share')), '\\\\server\\share')
        self.assertEqual(display(extended('C:\\a')), 'C:\\a')
        tree = scan('\\\\?\\' + str(self.root))
        self.assertEqual(tree.root, str(self.root))

    def test_denied_folder_is_reported_and_scan_goes_on(self):
        locked = self.root / 'locked'
        locked.mkdir()
        (locked / 'inside.txt').write_text('x')
        user = os.environ['USERNAME']
        subprocess.run(['icacls', str(locked), '/deny', f'{user}:(OI)(CI)(RD)'], check=True, capture_output=True)
        try:
            tree = scan(self.root)
        finally:
            subprocess.run(['icacls', str(locked), '/remove:d', user], check=True, capture_output=True)
        self.assertIn('locked', tree.names)
        self.assertNotIn('inside.txt', tree.names)
        self.assertEqual([(e.path, e.reason) for e in tree.errors], [(str(locked), 'access_denied')])
        self.assertIn('photo.png', tree.names)

    def test_depth_limit_is_reported(self):
        tree = scan(self.root, max_depth=0)
        self.assertEqual(sorted(e.path for e in tree.errors), [str(self.root / 'Alpha'), str(self.root / 'nested')])
        self.assertEqual({e.reason for e in tree.errors}, {'depth_limit'})
        self.assertNotIn('report.TXT', tree.names)

    def test_unicode_names(self):
        names = ['файл.txt', '文件.md', 'emoji 😀.txt', 'cafe\u0301.txt']
        for name in names:
            (self.root / name).write_text('x', encoding='utf-8')
        tree = scan(self.root)
        for name in names:
            self.assertGreaterEqual(tree.index_of(str(self.root / name)), 0, name)


class SafeCopyTests(TempTree):
    def test_copy_never_follows_a_looping_junction(self):
        (self.root / 'A').mkdir()
        (self.root / 'A' / 'a.txt').write_text('a')
        junction(self.root / 'A' / 'loop', self.root / 'A')
        report = fsops.copy_tree(self.root / 'A', self.root / 'B')
        self.assertEqual(report.links, 1)
        self.assertTrue(os.path.isjunction(self.root / 'B' / 'loop'))
        self.assertEqual(sorted(os.listdir(self.root / 'B')), ['a.txt', 'loop'])
        self.assertEqual(os.path.realpath(self.root / 'B' / 'loop'), str(self.root / 'A'))

    def test_copy_does_not_pull_outside_content(self):
        outside = self.base / 'outside'
        outside.mkdir()
        (outside / 'big.bin').write_bytes(b'x' * 1000)
        (self.root / 'A').mkdir()
        junction(self.root / 'A' / 'out', outside)
        fsops.copy_tree(self.root / 'A', self.root / 'B')
        self.assertTrue(os.path.isjunction(self.root / 'B' / 'out'))
        # Nessuna copia reale del contenuto esterno (os.walk seguirebbe la junction: si usa lo scanner)
        # No real copy of the outside content (os.walk would follow the junction: use the scanner)
        copied = scan(self.root / 'B')
        self.assertNotIn('big.bin', copied.names)
        self.assertEqual(copied.links, 1)

    def test_remove_tree_keeps_junction_targets(self):
        outside = self.base / 'outside'
        outside.mkdir()
        (outside / 'keep.txt').write_text('x')
        (self.root / 'A').mkdir()
        junction(self.root / 'A' / 'out', outside)
        fsops.remove_tree(self.root / 'A')
        self.assertFalse((self.root / 'A').exists())
        self.assertTrue((outside / 'keep.txt').exists())

    def test_move_and_copy_keep_content_and_dates(self):
        os.utime(self.root / 'nested' / 'report.TXT', (1_600_000_000, 1_600_000_000))
        fsops.copy_tree(self.root / 'nested', self.root / 'copy')
        self.assertEqual((self.root / 'copy' / 'report.TXT').read_text(), 'report')
        self.assertEqual(int((self.root / 'copy' / 'report.TXT').stat().st_mtime), 1_600_000_000)
        fsops.move(self.root / 'copy', self.root / 'Alpha' / 'moved')
        self.assertFalse((self.root / 'copy').exists())
        self.assertTrue((self.root / 'Alpha' / 'moved' / 'report.TXT').exists())


if __name__ == '__main__':
    unittest.main()
