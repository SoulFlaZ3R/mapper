"""Esclusioni (stile .gitignore), livelli ed esportazione TXT/Markdown/JSON/CSV.
Exclusions (.gitignore style), levels and TXT/Markdown/JSON/CSV export."""
import csv
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import reference_scanner_v15 as legacy  # noqa: E402
from mapper_core import export, scan  # noqa: E402
from mapper_core.export import ExportOptions, csv_safe, md_code, md_text  # noqa: E402
from mapper_core.filters import TECHNICAL, Excludes  # noqa: E402

GENERATED = datetime(2026, 10, 14, 8, 30, tzinfo=timezone.utc)


class FilterTests(unittest.TestCase):
    def check(self, patterns, cases):
        rules = Excludes(patterns)
        for rel, is_dir, expected in cases:
            self.assertEqual(rules.excluded(rel, rel.rsplit('/', 1)[-1], is_dir), expected, (patterns, rel, is_dir))

    def test_names_match_at_any_depth(self):
        self.check(['*.log', 'node_modules/'], [
            ('a.log', False, True), ('deep/x/b.LOG', False, True), ('a.logs', False, False),
            ('node_modules', True, True), ('src/node_modules', True, True), ('node_modules', False, False)])

    def test_anchored_and_double_star(self):
        self.check(['/build', 'docs/**/*.tmp', '**/cache/', 'a/**'], [
            ('build', True, True), ('src/build', True, False), ('docs/x.tmp', False, True),
            ('docs/a/b/x.tmp', False, True), ('other/x.tmp', False, False), ('cache', True, True),
            ('x/y/cache', True, True), ('a/b/c', False, True), ('a', True, False)])

    def test_negation_classes_and_escapes(self):
        self.check(['*.log', '!keep.log', 'a?c', '[!x]y.txt', '\\#notes', '\\!bang'], [
            ('x.log', False, True), ('keep.log', False, False), ('abc', False, True), ('abbc', False, False),
            ('zy.txt', False, True), ('xy.txt', False, False), ('#notes', False, True), ('!bang', False, True)])

    def test_text_comments_and_preset(self):
        rules = Excludes.from_text('# comment\n\n*.tmp\r\n', technical=True)
        self.assertEqual(rules.patterns, list(TECHNICAL) + ['*.tmp'])
        self.assertTrue(rules.excluded('.git', '.git', True))
        self.assertFalse(Excludes.from_text('# only a comment\n'))


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve() / 'root'
        (self.root / 'src' / 'deep').mkdir(parents=True)
        (self.root / 'src' / 'deep' / 'main.py').write_text('print(1)')
        (self.root / 'src' / 'app.log').write_text('log')
        (self.root / 'node_modules' / 'pkg').mkdir(parents=True)
        (self.root / 'node_modules' / 'pkg' / 'index.js').write_text('x')
        (self.root / '=SUM(A1).csv').write_text('a')
        (self.root / 'Résumé `v2`.md').write_bytes(b'x' * 2048)
        for path in self.root.rglob('*'):
            os.utime(path, (1_700_000_000, 1_700_000_000))
        self.tree = scan(self.root)
        self.options = ExportOptions(version='9.9.9', generated=GENERATED)

    def tearDown(self):
        import shutil
        shutil.rmtree(chr(92) * 2 + '?' + chr(92) + str(Path(self.temp.name).resolve()), ignore_errors=True)
        self.temp.cleanup()

    def test_exclusions_and_levels_shape_the_scan(self):
        tree = scan(self.root, excludes=Excludes.from_text('*.log', technical=True))
        self.assertNotIn('node_modules', tree.names)
        self.assertNotIn('app.log', tree.names)
        self.assertEqual(tree.excluded, 2)
        self.assertEqual(tree.patterns[-1], '*.log')
        shallow = scan(self.root, levels=1)
        self.assertEqual([shallow.names[i] for i in shallow.children()], ['node_modules', 'src', '=SUM(A1).csv', 'Résumé `v2`.md'])
        self.assertEqual((len(shallow), shallow.truncated, shallow.errors), (4, 2, []))
        self.assertEqual(list(shallow.lines())[1:3], ['├── node_modules/', '├── src/'])

    def test_txt_is_the_1_5_map_and_supports_subtrees(self):
        self.assertEqual(export.text(self.tree, 'txt', self.options), '\n'.join(legacy.scan_folder(str(self.root))))
        src = self.tree.index_of(str(self.root / 'src'))
        self.assertEqual(list(export.lines(self.tree, 'txt', ExportOptions(subtree=src))),
                         ['src/', '├── deep/', '│   └── main.py', '└── app.log'])

    def test_json_schema_paths_and_metadata(self):
        data = json.loads(export.text(self.tree, 'json', self.options))
        self.assertEqual((data['format'], data['version']), ('mapper-tree', 1))
        self.assertEqual(data['generator'], {'name': 'Mapper', 'version': '9.9.9'})
        self.assertEqual(data['generated'], '2026-10-14T08:30:00Z')
        self.assertEqual(data['root'], {'name': 'root', 'path': str(self.root)})
        self.assertEqual(data['summary']['items'], len(self.tree))
        self.assertEqual(data['summary']['bytes'], 8 + 3 + 1 + 1 + 2048)
        entries = {e['path']: e for e in data['entries']}
        main = entries['src/deep/main.py']
        self.assertEqual((main['type'], main['depth'], main['extension'], main['size']), ('file', 2, '.py', 8))
        self.assertEqual(main['modified'], '2023-11-14T22:13:20.000Z')
        self.assertIn('archive', main['attributes'])
        self.assertEqual([e['path'] for e in data['entries']][:2], ['node_modules', 'node_modules/pkg'])
        self.assertEqual(data['errors'], [])

    def test_json_subtree_redaction_and_no_metadata(self):
        src = self.tree.index_of(str(self.root / 'src'))
        output = export.text(self.tree, 'json', ExportOptions(subtree=src, redact=True, metadata=False, generated=GENERATED))
        self.assertNotIn(str(self.root).replace('\\', '\\\\'), output)
        self.assertNotIn(self.temp.name.replace('\\', '\\\\'), output)
        data = json.loads(output)
        self.assertEqual(data['root'], {'name': 'src', 'path': None})
        self.assertEqual([(e['path'], e['depth']) for e in data['entries']], [('deep', 0), ('deep/main.py', 1), ('app.log', 0)])
        self.assertNotIn('size', data['entries'][1])
        self.assertIsNone(data['summary']['bytes'])

    def test_json_lists_errors_relative_to_the_root(self):
        tree = scan(self.root)
        from mapper_core.model import ScanError
        tree.errors.append(ScanError(str(self.root / 'src' / 'locked'), 'access_denied'))
        data = json.loads(export.text(tree, 'json', ExportOptions(redact=True, generated=GENERATED)))
        self.assertEqual(data['errors'], [{'path': 'src/locked', 'reason': 'access_denied'}])

    def test_csv_is_safe_for_spreadsheets(self):
        rows = list(csv.reader(io.StringIO(export.text(self.tree, 'csv', self.options))))
        self.assertEqual(rows[0], list(export.CSV_COLUMNS))
        by_name = {row[1]: row for row in rows[1:]}
        self.assertIn("'=SUM(A1).csv", by_name)
        self.assertEqual(by_name["'=SUM(A1).csv"][0], "'=SUM(A1).csv")
        self.assertEqual(by_name['main.py'][:6], ['src/deep/main.py', 'main.py', 'file', '2', '.py', '8'])
        for text in ('=1+1', '+1', '-1', '@x', '\tx', '\rx'):
            self.assertTrue(csv_safe(text).startswith("'"), text)
        self.assertEqual(csv_safe('normal'), 'normal')

    def test_markdown_document(self):
        text = export.text(self.tree, 'md', self.options)
        self.assertTrue(text.startswith('# root\n'))
        self.assertIn('| Content | folders: 4 · files: 5 · links: 0 |', text)
        self.assertIn('| Total size | 2.0 KB |', text)
        # Un nome con ` richiede un recinto più lungo / A name with ` needs a longer fence
        self.assertIn('```text\nroot/', text)
        self.assertIn('| `.py` | 1 | 8 B |', text)
        self.assertEqual(md_code('a`b'), '``a`b``')
        self.assertEqual(md_text('a|b*c'), 'a\\|b\\*c')
        hidden = export.text(self.tree, 'md', ExportOptions(redact=True, generated=GENERATED))
        self.assertIn('| Path | *hidden* |', hidden)
        self.assertNotIn(str(self.root), hidden)

    def test_write_is_atomic_bom_crlf_and_long_paths(self):
        target = Path(self.temp.name) / 'out.csv'
        self.assertTrue(export.write(self.tree, 'csv', target, self.options))
        data = target.read_bytes()
        self.assertTrue(data.startswith(b'\xef\xbb\xbfpath,name'))
        self.assertIn(b'\r\n', data)
        txt = Path(self.temp.name) / 'out.txt'
        export.write(self.tree, 'txt', txt, self.options)
        self.assertEqual(txt.read_text(encoding='utf-8').splitlines(), legacy.scan_folder(str(self.root)))
        # Annullato: la destinazione resta com'era e non restano file temporanei
        # Cancelled: the destination stays as it was and no temporary file is left
        txt.write_text('previous', encoding='utf-8')
        cancel = threading.Event()
        cancel.set()
        self.assertFalse(export.write(self.tree, 'json', txt, self.options, cancel))
        self.assertEqual(txt.read_text(encoding='utf-8'), 'previous')
        self.assertEqual([p.name for p in Path(self.temp.name).iterdir() if p.name.startswith('.mapper-')], [])
        deep = self.temp.name + ''.join('\\' + 'segment_%02d_' % i + 'x' * 24 for i in range(9))
        os.makedirs('\\\\?\\' + deep)
        self.assertTrue(export.write(self.tree, 'md', deep + '\\map.md', self.options))
        self.assertTrue(os.path.exists('\\\\?\\' + deep + '\\map.md'))

    def test_unknown_format(self):
        with self.assertRaises(ValueError):
            export.text(self.tree, 'xml')


if __name__ == '__main__':
    unittest.main()
