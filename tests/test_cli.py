"""mapper-cli: comandi, codici di uscita, output JSON, log e assenza di Qt.
mapper-cli: commands, exit codes, JSON output, logging and no Qt."""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import mapper_cli  # noqa: E402
import reference_scanner_v15 as legacy  # noqa: E402


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / 'root'
        (self.root / 'docs').mkdir(parents=True)
        (self.root / 'docs' / 'guide.md').write_text('guide')
        (self.root / '.git').mkdir()
        (self.root / '.git' / 'HEAD').write_text('ref')
        (self.root / 'app.log').write_text('log')
        (self.root / 'main.py').write_text('print(1)')

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = mapper_cli.main([str(a) for a in argv])
        return code, out.getvalue(), err.getvalue()

    def test_scan_summary_with_exclusions_and_levels(self):
        code, out, _ = self.run_cli('scan', self.root, '--skip-technical', '--exclude', '*.log')
        summary = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual((summary['items'], summary['files'], summary['excluded']), (3, 2, 2))
        self.assertEqual(summary['extensions'], {'.md': 1, '.py': 1})
        patterns = self.base / 'patterns.txt'
        patterns.write_text('# comment\n*.py\n', encoding='utf-8')
        code, out, _ = self.run_cli('scan', self.root, '--exclude-from', patterns, '--levels', '1')
        summary = json.loads(out)
        self.assertEqual((summary['items'], summary['beyond_levels'], summary['excluded']), (3, 2, 1))
        self.assertEqual(self.run_cli('scan', self.root, '--levels', '-1')[0], 2)
        self.assertEqual(self.run_cli('scan', self.root, '--exclude', '[z-a]')[0], 3)
        self.assertEqual(self.run_cli('scan', self.base / 'missing')[0], 3)
        self.assertEqual(self.run_cli('scan', self.root, '--exclude-from', self.base / 'none.txt')[0], 4)

    def test_export_formats_subtree_and_output_rules(self):
        code, out, _ = self.run_cli('export', self.root)
        self.assertEqual((code, out), (0, '\n'.join(legacy.scan_folder(str(self.root))) + '\n'))
        code, out, _ = self.run_cli('export', self.root, '-f', 'json', '--subtree', 'docs', '--hide-paths')
        data = json.loads(out)
        self.assertEqual((data['root'], [e['path'] for e in data['entries']]), ({'name': 'docs', 'path': None}, ['guide.md']))
        self.assertEqual(self.run_cli('export', self.root, '--subtree', 'main.py')[0], 3)
        target = self.base / 'map.csv'
        code, out, err = self.run_cli('export', self.root, '-f', 'csv', '-o', target)
        self.assertEqual((code, out), (0, ''))
        self.assertTrue(target.read_bytes().startswith(b'\xef\xbb\xbfpath,'))
        self.assertIn('saved', err)
        self.assertEqual(self.run_cli('export', self.root, '-o', self.base)[0], 3)
        self.assertEqual(self.run_cli('export', self.root, '-o', self.base / 'missing' / 'x.txt')[0], 4)

    def test_snapshot_validate_and_diff_exit_codes(self):
        before = self.base / 'before.json'
        self.assertEqual(self.run_cli('snapshot', self.root, '-o', before, '--hashes', '-q')[0], 0)
        code, out, _ = self.run_cli('validate', before)
        report = json.loads(out)
        self.assertEqual((code, report['valid'], report['entries'], report['hashes']), (0, True, 6, True))
        # Nessuna differenza: 0 / No differences: 0
        code, out, _ = self.run_cli('diff', before, self.root, '-q')
        self.assertEqual((code, json.loads(out)['summary']['added']), (0, 0))
        (self.root / 'main.py').write_text('print(2)')
        (self.root / 'new.txt').write_text('new')
        code, out, err = self.run_cli('diff', before, self.root)
        data = json.loads(out)
        self.assertEqual(code, 1)
        self.assertEqual({(c['change'], c['path']) for c in data['changes']}, {('added', 'new.txt'), ('modified', 'main.py')})
        self.assertIn('added: 1', err)
        after = self.base / 'after.json'
        self.run_cli('snapshot', self.root, '-o', after, '-q')
        code, out, _ = self.run_cli('diff', before, after, '-f', 'md')
        self.assertEqual(code, 1)
        self.assertTrue(out.startswith('# Comparison: root → root'))
        bad = self.base / 'bad.json'
        bad.write_text('{"format": "mapper-tree", "version": 1, "entries": [{"path": "C:/x", "type": "file"}]}', encoding='utf-8')
        code, out, _ = self.run_cli('validate', bad)
        self.assertEqual((code, json.loads(out)), (3, {'valid': False, 'error': 'snapshot_invalid', 'detail': 'entry 1'}))
        self.assertEqual(self.run_cli('validate', self.base / 'missing.json')[0], 4)
        self.assertEqual(self.run_cli('diff', bad, self.root, '-q')[0], 3)

    def test_strict_mode_and_json_logs(self):
        locked = self.root / 'locked'
        locked.mkdir()
        user = os.environ['USERNAME']
        subprocess.run(['icacls', str(locked), '/deny', f'{user}:(OI)(CI)(RD)'], check=True, capture_output=True)
        try:
            code, out, err = self.run_cli('scan', self.root, '--strict', '--log-json')
            plain = self.run_cli('scan', self.root)
            quiet = self.run_cli('scan', self.root, '-q')
        finally:
            subprocess.run(['icacls', str(locked), '/remove:d', user], check=True, capture_output=True)
        self.assertEqual(code, 5)
        self.assertEqual(json.loads(out)['errors'], [{'path': str(locked), 'reason': 'access_denied'}])
        record = json.loads(err.splitlines()[0])
        self.assertEqual((record['level'], record['event'], record['reason']), ('info', 'not_readable', 'access_denied'))
        self.assertEqual(plain[0], 0)
        self.assertEqual(quiet[2], '')

    def test_version_and_usage(self):
        with self.assertRaises(SystemExit) as raised, contextlib.redirect_stdout(io.StringIO()) as out:
            mapper_cli.main(['--version'])
        self.assertEqual((raised.exception.code, out.getvalue().strip()), (0, f'mapper-cli {mapper_cli.VERSION}'))
        with self.assertRaises(SystemExit) as raised, contextlib.redirect_stderr(io.StringIO()):
            mapper_cli.main(['unknown-command'])
        self.assertEqual(raised.exception.code, 2)

    def test_real_process_utf8_and_no_qt(self):
        (self.root / 'Résumé 文件.txt').write_text('x', encoding='utf-8')
        env = dict(os.environ, PYTHONIOENCODING='cp1252')
        done = subprocess.run([sys.executable, str(SRC / 'mapper_cli.py'), 'export', str(self.root), '-f', 'json', '-q'],
                              capture_output=True, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        names = [e['name'] for e in json.loads(done.stdout.decode('utf-8'))['entries']]
        self.assertIn('Résumé 文件.txt', names)
        probe = subprocess.run([sys.executable, '-c', 'import sys; sys.path.insert(0, sys.argv[1]); import mapper_cli; '
                                'print(any(m.startswith(("PySide6", "shiboken6")) for m in sys.modules))', str(SRC)],
                               capture_output=True, text=True)
        self.assertEqual(probe.stdout.strip(), 'False')


if __name__ == '__main__':
    unittest.main()
