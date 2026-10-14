"""
Test di regressione di sicurezza aggiunti nella Milestone 5 (gli altri sono elencati in docs/security.md).
Security regression tests added in Milestone 5 (the others are listed in docs/security.md).
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from PySide6.QtCore import QCoreApplication
from backend import MapperBackend, explorer_path, is_program, redact_home
from mapper import bundled_only

APP = QCoreApplication.instance() or QCoreApplication([])


class OpenAndExplorerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        (self.root / 'setup.EXE').write_text('MZ')
        (self.root / 'notes.txt').write_text('notes')
        (self.root / 'tools.exe').mkdir()
        config = self.root / 'config.json'
        config.write_text(json.dumps(dict(language='en')), encoding='utf-8')
        self.backend = MapperBackend(config)
        self.backend.setPath(str(self.root))
        self.asked = []
        self.backend.runRequested.connect(self.asked.append)

    def tearDown(self):
        self.backend.shutdown()
        self.temp.cleanup()

    def test_programs_ask_before_running(self):
        with mock.patch('backend.QDesktopServices.openUrl', return_value=True) as open_url:
            self.backend.openPath(str(self.root / 'setup.EXE'))
            self.assertEqual(self.asked, [str(self.root / 'setup.EXE')])
            open_url.assert_not_called()
            self.backend.runProgram(str(self.root / 'setup.EXE'))
            self.assertEqual(open_url.call_count, 1)
            # Documenti e cartelle (anche se chiamate .exe) si aprono subito / Documents and folders open right away
            self.backend.openPath(str(self.root / 'notes.txt'))
            self.backend.openPath(str(self.root / 'tools.exe'))
            self.assertEqual(open_url.call_count, 3)
            self.assertEqual(len(self.asked), 1)

    def test_run_outside_the_mapped_folder_is_refused(self):
        outside = Path(tempfile.gettempdir()) / 'mapper-outside.bat'
        with mock.patch('backend.QDesktopServices.openUrl', return_value=True) as open_url:
            self.backend.runProgram(str(outside))
            self.backend.runProgram(str(self.root / '..' / outside.name))
        open_url.assert_not_called()
        self.assertTrue(self.backend.state['error'])

    def test_program_extensions(self):
        for name in ('a.exe', 'b.BAT', 'c.cmd', 'd.ps1', 'e.vbs', 'f.lnk', 'g.msi', 'h.js', 'i.hta', 'j.scr'):
            self.assertTrue(is_program(self.root / name), name)
        for name in ('a.txt', 'b.pdf', 'c.png', 'README', 'exe', 'd.exe.txt'):
            self.assertFalse(is_program(self.root / name), name)

    def test_explorer_is_started_by_absolute_path(self):
        with mock.patch('backend.subprocess.Popen') as popen:
            self.backend.showInFolder(str(self.root / 'notes.txt'))
        args = popen.call_args.args[0]
        self.assertEqual(args, [explorer_path(), '/select,' + str(self.root / 'notes.txt')])
        self.assertTrue(os.path.isabs(args[0]))
        self.assertEqual(os.path.dirname(args[0]).lower(), os.environ['SystemRoot'].lower())
        self.assertNotIn('shell', popen.call_args.kwargs)


class LaunchHardeningTests(unittest.TestCase):
    def test_qml_imports_only_from_bundle_and_resources(self):
        bundled = 'C:/App/_MEI123/PySide6/qml'
        paths = ['C:/Users/someone/Downloads', 'qrc:/qt-project.org/imports', 'qrc:/qt/qml',
                 'c:\\app\\_mei123\\PySide6\\qml', 'D:/elsewhere/qml']
        self.assertEqual(bundled_only(paths, bundled),
                         ['qrc:/qt-project.org/imports', 'qrc:/qt/qml', 'c:\\app\\_mei123\\PySide6\\qml'])

    def test_startup_log_hides_the_user_folder(self):
        home = os.path.normpath(os.path.expanduser('~'))
        text = f'File "{home}\\app\\x.py", line 1\nqml: {home.replace(os.sep, "/")}/Main.qml\n{home}2\\other'
        redacted = redact_home(text)
        self.assertNotIn(home + '\\', redacted)
        self.assertNotIn(home.replace(os.sep, '/') + '/', redacted)
        self.assertIn('%USERPROFILE%\\app\\x.py', redacted)
        self.assertIn('%USERPROFILE%/Main.qml', redacted)
        self.assertIn(home + '2\\other', redacted)  # un'altra cartella resta intatta / another folder is untouched


class SupplyChainTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    def test_actions_are_pinned_by_commit(self):
        for workflow in (self.ROOT / '.github' / 'workflows').glob('*.yml'):
            for line in workflow.read_text(encoding='utf-8').splitlines():
                if 'uses:' in line and not line.lstrip().startswith('#'):
                    self.assertRegex(line, r'uses: [\w.-]+/[\w.-]+@[0-9a-f]{40}  # v\d+\.\d+\.\d+$', line)

    def test_ci_installs_only_locked_hashed_packages(self):
        text = (self.ROOT / '.github' / 'workflows' / 'build-and-sign.yml').read_text(encoding='utf-8')
        installs = [line for line in text.splitlines() if 'pip install' in line]
        self.assertEqual(len(installs), 2)
        for line in installs:
            self.assertIn('--require-hashes', line)
            self.assertIn('-r build/requirements-', line)
        for lock in ('requirements-build.txt', 'requirements-tools.txt'):
            entries = (self.ROOT / 'build' / lock).read_text(encoding='utf-8').split('\n')
            packages = [line for line in entries if line[:1].isalnum()]
            self.assertTrue(packages, lock)
            for line in packages:
                self.assertRegex(line, r'^[\w.-]+==[\w.]+ \\$', f'{lock}: {line}')
                following = entries[entries.index(line) + 1]
                self.assertRegex(following, r'^    --hash=sha256:[0-9a-f]{64}', f'{lock}: {line}')


if __name__ == '__main__':
    unittest.main()
