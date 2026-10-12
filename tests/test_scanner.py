import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from scanner import count_items, root_label, scan_folder, snapshot


class ScannerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve() / 'root'
        (self.root / 'nested').mkdir(parents=True)
        (self.root / 'nested' / 'report.TXT').write_text('report')
        (self.root / 'desktop.ini').write_text('ignored')
        (self.root / 'photo.png').write_text('image')
        (self.root / 'Alpha').mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_tree_lines_records_and_counts(self):
        records, lines, counts, folders, files = snapshot(str(self.root))
        self.assertEqual(lines, ['root/', '├── Alpha/', '├── nested/', '│   └── report.TXT', '└── photo.png'])
        self.assertEqual([r['level'] for r in records], [0, 0, 1, 0])
        self.assertEqual(records[2]['parentPath'], str(self.root / 'nested'))
        self.assertEqual((folders, files), (2, 2))
        self.assertEqual(counts, {'.txt': 1, '.png': 1})
        self.assertEqual(scan_folder(str(self.root)), lines)

    def test_progress_matches_count(self):
        progress = []
        snapshot(str(self.root), progress_cb=progress.append)
        self.assertEqual(count_items(str(self.root)), 4)
        self.assertEqual(progress, [1, 2, 3, 4])

    def test_cancelled_scan(self):
        cancel = threading.Event()
        cancel.set()
        self.assertEqual(scan_folder(str(self.root), cancel), ['root/'])
        self.assertEqual(count_items(str(self.root), cancel), 0)

    def test_drive_root_label(self):
        self.assertEqual(root_label('D:\\'), 'D:/')
        self.assertEqual(root_label('C:\\Users\\me\\'), 'me/')

    @unittest.skipUnless(sys.platform == 'win32', 'NTFS junctions are Windows-only')
    def test_junctions_are_not_traversed(self):
        link = self.root / 'nested' / 'loop'
        subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(self.root)], check=True, capture_output=True)
        try:
            lines = scan_folder(str(self.root))
            self.assertIn('│   ├── loop', lines)
            self.assertEqual(count_items(str(self.root)), 5)
        finally:
            link.rmdir()


if __name__ == '__main__':
    unittest.main()
