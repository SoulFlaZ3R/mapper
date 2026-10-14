"""Snapshot (creazione, caricamento, validazione di file ostili) e confronto tra due stati.
Snapshots (creation, loading, validation of hostile files) and comparison between two states."""
import csv
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from mapper_core import diff, export, scan, snapshot  # noqa: E402
from mapper_core.diff import DiffExportOptions  # noqa: E402
from mapper_core.export import ExportOptions  # noqa: E402
from mapper_core.snapshot import Item, Snapshot, SnapshotError  # noqa: E402

GENERATED = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)
T0, T1 = 1_700_000_000, 1_800_000_000


def state(items, name='s', hashes=False):
    """Snapshot in memoria da {percorso: (tipo, dimensione, data, contenuto)} / In-memory snapshot."""
    snap = Snapshot(name, 'C:\\' + name)
    for path, (kind, size, mtime, content) in items.items():
        sha = hashlib.sha256(content.encode()).hexdigest() if hashes and kind == 'file' else None
        snap.add(Item(path, kind, size, mtime, sha))
    return snap


def kinds(result):
    return sorted((c.kind, c.detail, c.old_path if c.kind == 'renamed' else '', c.path, c.verified) for c in result.changes)


class CompareTests(unittest.TestCase):
    def test_real_folder_snapshot_and_targeted_verification(self):
        base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, base)
        root = base / 'proj'
        (root / 'docs' / 'old').mkdir(parents=True)
        for name, text in (('docs/old/a.md', 'alpha'), ('docs/old/b.md', 'bravo'), ('main.py', 'print(1)'),
                           ('same.txt', 'AAAA'), ('touched.txt', 'keep'), ('gone.txt', 'bye'), ('report.pdf', 'pdf!')):
            (root / name).write_text(text)
        for path in root.rglob('*'):
            os.utime(path, (T0, T0))
        snap_file = base / 'before.json'
        export.write(scan(root), 'json', snap_file, ExportOptions(hashes=True))
        (root / 'main.py').write_text('print(12345)')
        (root / 'same.txt').write_text('BBBB')
        os.utime(root / 'touched.txt', (T1, T1))
        (root / 'gone.txt').unlink()
        (root / 'new.txt').write_text('hello')
        os.rename(root / 'report.pdf', root / 'final.pdf')
        shutil.move(str(root / 'docs' / 'old'), str(root / 'archive'))
        reads = []
        def verify(rel):
            reads.append(rel)
            return export.sha256_file(root / rel)
        before = snapshot.load(snap_file)
        self.assertTrue(before.has_hashes)
        result = diff.compare(before, Snapshot.from_tree(scan(root)), verify=verify)
        self.assertEqual(kinds(result), sorted([
            ('renamed', 'folder', 'docs/old', 'archive', False), ('removed', '', '', 'gone.txt', False),
            ('added', '', '', 'new.txt', False), ('renamed', 'size_date', 'report.pdf', 'final.pdf', False),
            ('modified', 'content', '', 'same.txt', True), ('modified', 'content', '', 'main.py', False),
            ('modified', 'metadata', '', 'touched.txt', True)]))
        # Solo i file dubbi vengono riletti / Only doubtful files are read again
        self.assertEqual(sorted(reads), ['same.txt', 'touched.txt'])
        self.assertTrue(result.hashes_used)

    def test_dates_alone_never_mean_content(self):
        old = state({'a.txt': ('file', 4, T0, 'AAAA')})
        new = state({'a.txt': ('file', 4, T1, 'BBBB')})
        self.assertEqual(kinds(diff.compare(old, new)), [('modified', 'metadata', '', 'a.txt', False)])
        old_h = state({'a.txt': ('file', 4, T0, 'AAAA')}, hashes=True)
        new_h = state({'a.txt': ('file', 4, T0, 'BBBB')}, hashes=True)
        self.assertEqual(kinds(diff.compare(old_h, new_h)), [('modified', 'content', '', 'a.txt', True)])
        same = state({'a.txt': ('file', 4, T1, 'AAAA')}, hashes=True)
        self.assertEqual(kinds(diff.compare(old_h, same)), [('modified', 'metadata', '', 'a.txt', True)])

    def test_type_change_and_folder_dates_ignored(self):
        old = state({'x': ('file', 1, T0, 'x'), 'd': ('dir', -1, T0, '')})
        new = state({'x': ('dir', -1, T0, ''), 'd': ('dir', -1, T1, '')})
        result = diff.compare(old, new)
        self.assertEqual(kinds(result), [('modified', 'type', '', 'x', False)])
        self.assertEqual(result.unchanged, 1)

    def test_ambiguous_renames_are_not_guessed(self):
        old = state({'a.txt': ('file', 5, T0, 'same!'), 'b.txt': ('file', 5, T0, 'same!')})
        new = state({'c.txt': ('file', 5, T0, 'same!'), 'd.txt': ('file', 5, T0, 'same!')})
        self.assertEqual({c.kind for c in diff.compare(old, new).changes}, {'added', 'removed'})
        empty_old = state({'e1': ('file', 0, T0, '')})
        empty_new = state({'e2': ('file', 0, T0, '')})
        self.assertEqual({c.kind for c in diff.compare(empty_old, empty_new).changes}, {'added', 'removed'})
        # Rinomina per hash: unica e verificata / Rename by hash: unique and verified
        old_h = state({'a.bin': ('file', 3, T0, 'abc')}, hashes=True)
        new_h = state({'z/b.dat': ('file', 3, T1, 'abc'), 'z': ('dir', -1, T1, '')}, hashes=True)
        self.assertIn(('renamed', 'hash', 'a.bin', 'z/b.dat', True), kinds(diff.compare(old_h, new_h)))

    def test_folder_moves_need_a_unique_non_empty_signature(self):
        old = state({'one': ('dir', -1, T0, ''), 'one/f.txt': ('file', 2, T0, 'ab'),
                     'two': ('dir', -1, T0, ''), 'two/f.txt': ('file', 2, T0, 'ab'), 'empty': ('dir', -1, T0, '')})
        new = state({'uno': ('dir', -1, T0, ''), 'uno/f.txt': ('file', 2, T0, 'ab'),
                     'due': ('dir', -1, T0, ''), 'due/f.txt': ('file', 2, T0, 'ab'), 'vuota': ('dir', -1, T0, '')})
        self.assertNotIn('folder', {c.detail for c in diff.compare(old, new).changes})


class SnapshotFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp.name)
        root = self.dir / 'root'
        (root / 'sub').mkdir(parents=True)
        (root / 'sub' / 'f.txt').write_text('hello')
        self.tree = scan(root)
        self.good = self.dir / 'good.json'
        export.write(self.tree, 'json', self.good, ExportOptions(generated=GENERATED, hashes=True))

    def tearDown(self):
        self.temp.cleanup()

    def write(self, text, name='bad.json'):
        path = self.dir / name
        path.write_text(text, encoding='utf-8')
        return path

    def data(self):
        return json.loads(self.good.read_text(encoding='utf-8'))

    def assert_rejected(self, payload, key='snapshot_invalid'):
        text = payload if isinstance(payload, str) else json.dumps(payload)
        with self.assertRaises(SnapshotError) as raised:
            snapshot.load(self.write(text))
        self.assertEqual(raised.exception.key, key, raised.exception)

    def test_canonical_reformatted_and_bom_files_load(self):
        loaded = snapshot.load(self.good)
        self.assertEqual(sorted(i.path for i in loaded.items.values()), ['sub', 'sub/f.txt'])
        self.assertEqual(loaded.items['sub/f.txt'].sha256, hashlib.sha256(b'hello').hexdigest())
        self.assertEqual(loaded.items['sub/f.txt'].size, 5)
        pretty = self.write(json.dumps(self.data(), indent=3), 'pretty.json')
        self.assertEqual(len(snapshot.load(pretty)), 2)
        bom = self.dir / 'bom.json'
        bom.write_bytes(b'\xef\xbb\xbf' + self.good.read_bytes())
        self.assertEqual(len(snapshot.load(bom)), 2)

    def test_hostile_or_broken_files_are_rejected(self):
        good = self.data()
        def with_entry(entry):
            data = self.data()
            data['entries'] = [entry]
            return data
        self.assert_rejected(dict(good, format='other'), 'snapshot_not_mapper')
        self.assert_rejected(dict(good, version=99), 'snapshot_newer')
        self.assert_rejected(dict(good, version='1'), 'snapshot_not_mapper')
        self.assert_rejected(dict(good, options=dict(good['options'], metadata=False)), 'snapshot_no_metadata')
        for path in ('C:/Windows', '/etc/passwd', '../outside', 'a/../../b', 'a\\b', 'a//b', 'bad\x01name',
                     'name.', 'x' * 40000, '', 42):
            self.assert_rejected(with_entry({'path': path, 'type': 'file'}))
        self.assert_rejected(with_entry({'path': 'a', 'type': 'device'}))
        self.assert_rejected(with_entry({'path': 'a', 'type': 'file', 'size': 'big'}))
        self.assert_rejected(with_entry({'path': 'a', 'type': 'file', 'size': True}))
        self.assert_rejected(with_entry({'path': 'a', 'type': 'file', 'sha256': 'zz'}))
        self.assert_rejected(with_entry({'path': 'a', 'type': 'file', 'modified': 'yesterday'}))
        dup = self.data()
        dup['entries'] = [{'path': 'A.txt', 'type': 'file'}, {'path': 'a.TXT', 'type': 'file'}]
        self.assert_rejected(dup, 'snapshot_duplicate')
        self.assert_rejected(json.dumps(with_entry({'path': 'a', 'type': 'file'})).replace('"file"}', '"file", "size": NaN}'))
        self.assert_rejected('[' * 100000 + ']' * 100000)
        self.assert_rejected(self.good.read_text(encoding='utf-8')[:-40])
        self.assert_rejected('not json at all')
        with self.assertRaises(SnapshotError) as raised:
            snapshot.load(self.dir / 'missing.json')
        self.assertEqual(raised.exception.key, 'snapshot_unreadable')

    def test_size_limits(self):
        with mock.patch.object(snapshot, 'MAX_BYTES', 100):
            with self.assertRaises(SnapshotError) as raised:
                snapshot.load(self.good)
            self.assertEqual(raised.exception.key, 'snapshot_too_large')
        with mock.patch.object(snapshot, 'MAX_ENTRIES', 1):
            with self.assertRaises(SnapshotError) as raised:
                snapshot.load(self.good)
            self.assertEqual(raised.exception.key, 'snapshot_too_large')
        with mock.patch.object(snapshot, 'MAX_FALLBACK_BYTES', 10):
            pretty = self.write(json.dumps(self.data(), indent=3), 'pretty.json')
            with self.assertRaises(SnapshotError):
                snapshot.load(pretty)


class DiffExportTests(unittest.TestCase):
    def setUp(self):
        old = state({'keep.txt': ('file', 1, T0, 'k'), 'old.txt': ('file', 3, T0, 'old'), 'gone': ('file', 2, T0, 'go'),
                     '=cmd.txt': ('file', 4, T0, 'evil')}, 'before', hashes=True)
        new = state({'keep.txt': ('file', 1, T0, 'k'), 'new.txt': ('file', 3, T1, 'old'), 'added': ('file', 5, T1, 'added'),
                     '=cmd.txt': ('file', 5, T1, 'evil!')}, 'after', hashes=True)
        self.result = diff.compare(old, new)
        self.options = DiffExportOptions(version='9.9.9', generated=GENERATED)

    def test_json(self):
        data = json.loads(diff.text(self.result, 'json', self.options))
        self.assertEqual((data['format'], data['version']), ('mapper-diff', 1))
        self.assertEqual(data['old'], {'name': 'before', 'path': 'C:\\before', 'generated': None})
        self.assertEqual(data['summary']['renamed'], 1)
        renamed = next(c for c in data['changes'] if c['change'] == 'renamed')
        self.assertEqual((renamed['old_path'], renamed['path'], renamed['detail'], renamed['verified']),
                         ('old.txt', 'new.txt', 'hash', True))
        hidden = json.loads(diff.text(self.result, 'json', DiffExportOptions(redact=True, generated=GENERATED)))
        self.assertIsNone(hidden['old']['path'])
        self.assertNotIn('C:\\\\before', diff.text(self.result, 'json', DiffExportOptions(redact=True)))

    def test_csv_and_markdown(self):
        rows = list(csv.reader(io.StringIO(diff.text(self.result, 'csv', self.options))))
        self.assertEqual(rows[0], list(diff.CSV_COLUMNS))
        self.assertIn("'=cmd.txt", [row[1] for row in rows])
        md = diff.text(self.result, 'md', self.options)
        self.assertTrue(md.startswith('# Comparison: before → after'))
        self.assertIn('## Renamed or moved (1)', md)
        self.assertIn('| `old.txt` | `new.txt` | hash |', md)
        self.assertNotIn('C:\\before', diff.text(self.result, 'md', DiffExportOptions(redact=True)))

    def test_write_and_unknown_format(self):
        target = Path(tempfile.mkdtemp()) / 'diff.csv'
        self.addCleanup(shutil.rmtree, target.parent)
        self.assertTrue(diff.write(self.result, 'csv', target, self.options))
        self.assertTrue(target.read_bytes().startswith(b'\xef\xbb\xbfchange,path'))
        with self.assertRaises(ValueError):
            diff.text(self.result, 'txt')


if __name__ == '__main__':
    unittest.main()
