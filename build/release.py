"""
Prepara una release di Mapper in locale (commit + tag), senza mai fare push.
Prepares a Mapper release locally (commit + tag) and never pushes.

Uso / Usage (dalla root del progetto / from the project root):
  .venv\\Scripts\\python.exe build\\release.py patch|minor|major|X.Y.Z [--dry-run]
  .venv\\Scripts\\python.exe build\\release.py notes [--tag vX.Y.Z] [--out release-notes.md]

Release: branch main pulito → VERSION in src/mapper_core/version.py, titoli dei README, portable/README.txt e
CLAUDE.md aggiornati → la sezione [Unreleased] del CHANGELOG diventa [X.Y.Z] → test → commit
"Action: release" e tag annotato vX.Y.Z. Alla fine stampa i comandi di push.
Release: clean main branch → VERSION in src/mapper_core/version.py, README titles, portable/README.txt and
CLAUDE.md updated → the CHANGELOG [Unreleased] section becomes [X.Y.Z] → tests → "Action: release"
commit and annotated tag vX.Y.Z. Finally prints the push commands.

notes (GitHub Actions): controlla che il tag coincida con VERSION e scrive la sezione del
CHANGELOG di quella versione (testo della release).
notes (GitHub Actions): checks the tag matches VERSION and writes that version's CHANGELOG
section (the release text).
"""
import argparse
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_URL = 'https://github.com/SoulFlaZ3R/mapper'
SEMVER = re.compile(r'^(\d+)\.(\d+)\.(\d+)$')
# Riga di fine compresa: i file usano CRLF / End of line included: files use CRLF
EOL = r'(?=\r?$)'
VERSION_RE = re.compile(r"^VERSION = '(\d+\.\d+\.\d+)'" + EOL, re.M)
# (file, regex, sostituzione, obbligatorio) / (file, regex, replacement, required)
VERSION_SPOTS = [
    ('src/mapper_core/version.py', VERSION_RE, lambda v: f"VERSION = '{v}'", True),
    ('README.md', re.compile(r'^# Mapper \d+\.\d+(?:\.\d+)?' + EOL, re.M), lambda v: f'# Mapper {short(v)}', True),
    ('README.it.md', re.compile(r'^# Mapper \d+\.\d+(?:\.\d+)?' + EOL, re.M), lambda v: f'# Mapper {short(v)}', True),
    ('portable/README.txt', re.compile(r'^MAPPER \d+\.\d+(?:\.\d+)?(?= )', re.M), lambda v: f'MAPPER {short(v)}', True),
    # CLAUDE.md è locale (gitignored) / CLAUDE.md is local (gitignored)
    ('CLAUDE.md', re.compile(r'(?<=\*\*Version\*\*: )\d+\.\d+\.\d+'), lambda v: v, False),
]


class ReleaseError(Exception):
    pass


def short(version):
    """1.5.0 → 1.5 (titoli dei documenti / document titles)."""
    return '.'.join(version.split('.')[:2])


def parse(version):
    match = SEMVER.match(version)
    if not match:
        raise ReleaseError(f'"{version}" is not a version like 1.6.0')
    return tuple(int(n) for n in match.groups())


def next_version(current, bump):
    """patch/minor/major o versione esplicita / or an explicit version."""
    major, minor, patch = parse(current)
    if bump == 'patch':
        return f'{major}.{minor}.{patch + 1}'
    if bump == 'minor':
        return f'{major}.{minor + 1}.0'
    if bump == 'major':
        return f'{major + 1}.0.0'
    parse(bump)
    return bump


def read(path):
    # newline='' mantiene i CRLF / keeps CRLF line endings
    with open(path, encoding='utf-8', newline='') as handle:
        return handle.read()


def write(path, text):
    with open(path, 'w', encoding='utf-8', newline='') as handle:
        handle.write(text)


def current_version():
    match = VERSION_RE.search(read(ROOT / 'src' / 'mapper_core' / 'version.py'))
    if not match:
        raise ReleaseError("VERSION = 'X.Y.Z' not found in src/mapper_core/version.py")
    return match.group(1)


def heading(version):
    return re.compile(r'^## \[' + re.escape(version) + r'\][^\r\n]*\r?\n', re.M)


def released_versions(changelog):
    return re.findall(r'^## \[(\d+\.\d+\.\d+)\]', changelog, re.M)


def section(changelog, version):
    """Testo della sezione di una versione / Text of a version's section."""
    match = heading(version).search(changelog)
    if not match:
        raise ReleaseError(f'CHANGELOG.md has no "## [{version}]" section')
    rest = changelog[match.end():]
    end = re.search(r'^(## \[|\[[^\]]+\]: )', rest, re.M)
    body = (rest[:end.start()] if end else rest).replace('\r\n', '\n').strip()
    if not body:
        raise ReleaseError(f'CHANGELOG.md section [{version}] is empty')
    return body


def changelog_release(changelog, version, date):
    """[Unreleased] → [version] - date, con i link di confronto / with compare links."""
    nl = '\r\n' if '\r\n' in changelog else '\n'
    if version in released_versions(changelog):
        raise ReleaseError(f'CHANGELOG.md already has a [{version}] section')
    match = heading('Unreleased').search(changelog)
    if not match:
        raise ReleaseError('CHANGELOG.md has no "## [Unreleased]" section')
    try:
        section(changelog, 'Unreleased')
    except ReleaseError:
        raise ReleaseError('CHANGELOG.md [Unreleased] is empty: describe the changes first') from None
    previous = released_versions(changelog)
    text = changelog[:match.start()] + f'## [Unreleased]{nl}{nl}## [{version}] - {date}{nl}' + changelog[match.end():]
    # Link in fondo: [Unreleased] confronta con il nuovo tag / Bottom links: [Unreleased] compares with the new tag
    text = re.sub(r'^\[Unreleased\]: [^\r\n]*\r?\n?', '', text, flags=re.M).rstrip() + nl
    link = f'{REPO_URL}/compare/v{previous[0]}...v{version}' if previous else f'{REPO_URL}/releases/tag/v{version}'
    refs = f'[Unreleased]: {REPO_URL}/compare/v{version}...HEAD{nl}[{version}]: {link}{nl}'
    first_ref = re.search(r'^\[[^\]]+\]: ', text, re.M)
    if first_ref:
        return text[:first_ref.start()] + refs + text[first_ref.start():]
    return text + nl + refs


def set_version(text, pattern, replacement, version, name):
    new, count = pattern.subn(replacement(version), text)
    if count != 1:
        raise ReleaseError(f'{name}: expected 1 version mention, found {count}')
    return new


def git(*args, check=True):
    result = subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
    if check and result.returncode:
        raise ReleaseError(f'git {" ".join(args)} failed:\n{result.stderr.strip()}')
    return result.stdout.strip()


def check_repository(tag):
    branch = git('rev-parse', '--abbrev-ref', 'HEAD')
    if branch != 'main':
        raise ReleaseError(f'releases are made from the main branch (current: {branch})')
    if git('status', '--porcelain'):
        raise ReleaseError('the working tree has uncommitted changes: commit or discard them first')
    if git('tag', '--list', tag):
        raise ReleaseError(f'tag {tag} already exists locally')
    try:
        remote = subprocess.run(['git', 'ls-remote', '--tags', 'origin', f'refs/tags/{tag}'], cwd=ROOT,
                                capture_output=True, text=True, timeout=30)
        if remote.returncode == 0 and remote.stdout.strip():
            raise ReleaseError(f'tag {tag} already exists on GitHub')
        if remote.returncode:
            print(f'Avviso / Warning: could not check tags on GitHub ({remote.stderr.strip()})')
    except subprocess.TimeoutExpired:
        print('Avviso / Warning: GitHub did not answer, remote tags not checked')
    behind = git('rev-list', '--count', 'HEAD..origin/main', check=False)
    if behind.isdigit() and int(behind):
        raise ReleaseError(f'main is {behind} commit(s) behind origin/main: pull first')


def run_tests():
    env = dict(os.environ, PYTHONUTF8='1')
    for command in ([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py'],
                    [sys.executable, 'tests/smoke_ui.py']):
        print('>', ' '.join(command[1:]))
        if subprocess.run(command, cwd=ROOT, env=env).returncode:
            raise ReleaseError('tests failed: release not created')


def prepare(bump, dry_run):
    current = current_version()
    changelog_path = ROOT / 'CHANGELOG.md'
    changelog = read(changelog_path)
    version = next_version(current, bump)
    if parse(version) < parse(current) or (version == current and current in released_versions(changelog)):
        raise ReleaseError(f'{version} must be newer than the released {current}')
    tag = f'v{version}'
    try:
        check_repository(tag)
    except ReleaseError as error:
        if not dry_run:
            raise
        print(f'Avviso / Warning: a real release would stop here: {error}')
    now = datetime.now()
    files = {changelog_path: changelog_release(changelog, version, now.strftime('%Y-%m-%d'))}
    for name, pattern, replacement, required in VERSION_SPOTS:
        path = ROOT / name
        if not path.exists() and not required:
            continue
        files[path] = set_version(read(path), pattern, replacement, version, name)
    print(f'Release {current} -> {version} ({tag})\n')
    print(section(files[changelog_path], version), '\n')
    if dry_run:
        print('Prova: nessun file modificato / Dry run: no file changed')
        return
    originals = {path: read(path) for path in files}
    try:
        for path, text in files.items():
            write(path, text)
        run_tests()
    except BaseException:
        for path, text in originals.items():
            write(path, text)
        raise
    tracked = [str(path.relative_to(ROOT)) for path in files if git('ls-files', str(path.relative_to(ROOT)))]
    git('add', '--', *tracked)
    git('commit', '-q', '-m', f'{now:%d/%m/%Y %H:%M:%S} - MAPPER {tag} - Action: release - Details: release {tag}')
    git('tag', '-a', tag, '-m', f'Mapper {version}')
    print(f'''
Release {tag} pronta in locale / ready locally (commit + tag, nothing pushed).

1. Ricompila l'exe portable / Rebuild the portable exe:
     build\\build.bat
     portable\\Mapper.exe --smoke-test
2. Pubblica / Publish (the tag push starts GitHub Actions: tests, build, release):
     git push origin main
     git push origin {tag}

Annullare prima del push / Undo before pushing:
     git tag -d {tag}
     git reset --keep HEAD~1
''')


def notes(tag, out):
    version = current_version()
    if tag and tag != f'v{version}':
        raise ReleaseError(f"tag {tag} does not match VERSION = '{version}' in src/mapper_core/version.py")
    body = section(read(ROOT / 'CHANGELOG.md'), version)
    Path(out).write_text(body + '\n', encoding='utf-8')
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as handle:
            handle.write(f'version={version}\n')
    print(f'Version {version}: release notes written to {out}')


def main(argv=None):
    # Console Windows non UTF-8: niente crash sui caratteri speciali / Non-UTF-8 Windows console: no crash on symbols
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors='replace')
    parser = argparse.ArgumentParser(description='Mapper release helper (never pushes)')
    parser.add_argument('action', help='patch, minor, major, X.Y.Z, or notes')
    parser.add_argument('--dry-run', action='store_true', help='show the release without changing files')
    parser.add_argument('--tag', default='', help='notes: tag that must match VERSION (e.g. v1.6.0)')
    parser.add_argument('--out', default='release-notes.md', help='notes: output file')
    args = parser.parse_args(argv)
    try:
        if args.action == 'notes':
            notes(args.tag, args.out)
        else:
            prepare(args.action, args.dry_run)
    except ReleaseError as error:
        print(f'ERRORE / ERROR: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
