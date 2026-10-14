"""
Mapper da riga di comando: stesso motore dell'app (mapper_core), nessuna finestra, nessun Qt.
Mapper command line: same engine as the app (mapper_core), no window, no Qt.

  mapper-cli scan FOLDER          riepilogo JSON della mappatura / JSON summary of the mapping
  mapper-cli export FOLDER        mappa in txt, md, json o csv / map as txt, md, json or csv
  mapper-cli snapshot FOLDER      snapshot JSON (facoltativo: impronte SHA-256) / JSON snapshot (optional SHA-256)
  mapper-cli diff BEFORE AFTER    confronto tra snapshot o cartella attuale / snapshot or current folder comparison
  mapper-cli validate FILE        controlla uno snapshot / checks a snapshot

Codici di uscita / Exit codes:
  0 ok (diff: nessuna differenza / no differences)   1 diff: differenze trovate / differences found
  2 uso errato / wrong usage   3 input non valido / invalid input   4 errore di lettura o scrittura / I/O error
  5 --strict: elementi non leggibili / unreadable items   130 interrotto (Ctrl+C) / interrupted
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

from mapper_core import DIR, diff, export, scan, snapshot
from mapper_core.filters import Excludes
from mapper_core.paths import extended, normalize
from mapper_core.version import VERSION

OK, DIFFERENT, USAGE, INVALID, IO_ERROR, PARTIAL, INTERRUPTED = 0, 1, 2, 3, 4, 5, 130


class CliError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class Log:
    """
    Messaggi su stderr: testo semplice o righe JSON (--log-json); stdout resta solo per i risultati.
    Messages on stderr: plain text or JSON lines (--log-json); stdout is only for results.
    """

    def __init__(self, quiet=False, verbose=False, as_json=False):
        self.quiet, self.verbose, self.as_json = quiet, verbose, as_json

    def emit(self, level, event, message, **fields):
        if self.quiet and level != 'error' or level == 'debug' and not self.verbose:
            return
        if self.as_json:
            record = {'time': datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z'),
                      'level': level, 'event': event, 'message': message} | fields
            print(json.dumps(record, ensure_ascii=False), file=sys.stderr, flush=True)
        else:
            print(f'mapper-cli: {message}' if level != 'error' else f'mapper-cli: error: {message}',
                  file=sys.stderr, flush=True)

    def info(self, event, message, **fields):
        self.emit('info', event, message, **fields)

    def debug(self, event, message, **fields):
        self.emit('debug', event, message, **fields)

    def error(self, event, message, **fields):
        self.emit('error', event, message, **fields)


# ── Aiuti / Helpers ─────────────────────────────────────────────────────
def folder(path):
    """Cartella esistente, percorso assoluto normalizzato / Existing folder, absolute normalized path."""
    target = normalize(os.path.expanduser(path))
    if not os.path.isdir(extended(target)):
        raise CliError(INVALID, f'not a folder: {path}')
    return target


def output_path(path):
    """Il file di output non può essere una cartella; la sua cartella deve esistere / Output must be a file in an existing folder."""
    target = normalize(os.path.expanduser(path))
    if os.path.isdir(extended(target)):
        raise CliError(INVALID, f'output is a folder: {path}')
    if not os.path.isdir(extended(os.path.dirname(target))):
        raise CliError(IO_ERROR, f'output folder does not exist: {os.path.dirname(target)}')
    return target


def excludes_from(args):
    lines = list(args.exclude or [])
    for name in args.exclude_from or []:
        try:
            with open(extended(normalize(name)), encoding='utf-8-sig') as handle:
                lines += handle.read().splitlines()
        except OSError as exc:
            raise CliError(IO_ERROR, f'cannot read {name}: {exc.strerror}') from None
    try:
        return Excludes.from_text('\n'.join(lines), technical=args.skip_technical)
    except re.error:
        raise CliError(INVALID, 'invalid exclusion pattern') from None


def do_scan(args, log):
    root = folder(args.folder)
    excludes = excludes_from(args)
    levels = args.levels or None
    if levels is not None and levels < 1:
        raise CliError(USAGE, '--levels must be 1 or more')
    log.debug('scan_start', f'mapping {root}', root=root)
    started = time.perf_counter()
    tree = scan(root, excludes=excludes, levels=levels,
                progress=lambda n: log.debug('scan_progress', f'{n} items found', items=n), progress_every=50_000)
    elapsed = time.perf_counter() - started
    log.debug('scan_done', f'{len(tree)} items in {elapsed:.2f} s', items=len(tree), seconds=round(elapsed, 3))
    for error in tree.errors:
        log.info('not_readable', f'not readable ({error.reason}): {error.path}', path=error.path, reason=error.reason)
    return tree, elapsed


def subtree_index(tree, relative):
    if not relative:
        return -1
    index = tree.index_of(os.path.join(tree.root, relative.replace('/', os.sep)))
    if index < 0 or tree.kinds[index] != DIR:
        raise CliError(INVALID, f'not a folder inside the map: {relative}')
    return index


def emit_lines(lines, out, csv_format=False):
    """Su file (atomico) o su stdout in UTF-8 / To a file (atomic) or to stdout as UTF-8."""
    if out:
        try:
            export.write_lines(lines, output_path(out), csv_format=csv_format)
        except OSError as exc:
            raise CliError(IO_ERROR, f'cannot write {out}: {exc.strerror}') from None
        return
    for line in lines:
        sys.stdout.write(line + '\n')
    sys.stdout.flush()


def strict_code(args, tree):
    return PARTIAL if args.strict and tree.errors else OK


# ── Comandi / Commands ──────────────────────────────────────────────────
def cmd_scan(args, log):
    tree, elapsed = do_scan(args, log)
    summary = {
        'root': tree.root, 'items': len(tree), 'folders': tree.folders, 'files': tree.files, 'links': tree.links,
        'bytes': sum(s for s, k in zip(tree.sizes, tree.kinds) if k == 0 and s > 0), 'excluded': tree.excluded,
        'beyond_levels': tree.truncated, 'seconds': round(elapsed, 3),
        'extensions': dict(tree.extensions.most_common()),
        'errors': [{'path': e.path, 'reason': e.reason} for e in tree.errors],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2 if args.pretty else None))
    return strict_code(args, tree)


def cmd_export(args, log):
    tree, _ = do_scan(args, log)
    options = export.ExportOptions(subtree=subtree_index(tree, args.subtree), redact=args.hide_paths,
                                   metadata=not args.no_metadata, version=VERSION)
    emit_lines(export.lines(tree, args.format, options), args.out, args.format == 'csv')
    if args.out:
        log.info('saved', f'saved {args.out}', path=args.out)
    return strict_code(args, tree)


def cmd_snapshot(args, log):
    tree, _ = do_scan(args, log)
    if args.hashes:
        log.info('hashing', 'computing SHA-256 fingerprints (reads every file)')
    options = export.ExportOptions(metadata=True, hashes=args.hashes, redact=args.hide_paths, version=VERSION)
    emit_lines(export.lines(tree, 'json', options), args.out)
    if args.out:
        log.info('saved', f'snapshot saved {args.out}', path=args.out)
    return strict_code(args, tree)


def load_snapshot(path):
    try:
        return snapshot.load(path)
    except snapshot.SnapshotError as exc:
        code = IO_ERROR if exc.key == 'snapshot_unreadable' else INVALID
        raise CliError(code, f'{path}: {exc.key}' + (f' ({exc.detail})' if exc.detail else '')) from None


def cmd_diff(args, log):
    before = load_snapshot(args.before)
    target = normalize(os.path.expanduser(args.after))
    if os.path.isdir(extended(target)):
        args.folder = args.after
        tree, _ = do_scan(args, log)
        root = tree.root
        def verify(relative):
            log.debug('verify', f'checking content of {relative}', path=relative)
            return export.sha256_file(os.path.join(root, relative.replace('/', os.sep)))
        result = diff.compare(before, snapshot.Snapshot.from_tree(tree), verify=verify)
    else:
        result = diff.compare(before, load_snapshot(args.after))
    summary = result.summary()
    log.info('compared', ', '.join(f'{k}: {summary[k]}' for k in diff.KINDS), **summary)
    options = diff.DiffExportOptions(redact=args.hide_paths, version=VERSION)
    emit_lines(diff.lines(result, args.format, options), args.out, args.format == 'csv')
    return DIFFERENT if result.changes else OK


def cmd_validate(args, log):
    try:
        loaded = snapshot.load(args.file)
    except snapshot.SnapshotError as exc:
        report = {'valid': False, 'error': exc.key, 'detail': exc.detail}
        print(json.dumps(report, ensure_ascii=False))
        return IO_ERROR if exc.key == 'snapshot_unreadable' else INVALID
    report = {'valid': True, 'name': loaded.name, 'entries': len(loaded), 'hashes': loaded.has_hashes,
              'complete': loaded.complete, 'generated': loaded.generated}
    print(json.dumps(report, ensure_ascii=False))
    return OK


# ── Argomenti / Arguments ───────────────────────────────────────────────
def parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('-q', '--quiet', action='store_true', help='only errors on stderr')
    common.add_argument('-v', '--verbose', action='store_true', help='progress details on stderr')
    common.add_argument('--log-json', action='store_true', help='stderr messages as JSON lines')
    scan_options = argparse.ArgumentParser(add_help=False)
    scan_options.add_argument('--exclude', action='append', metavar='PATTERN', help='.gitignore-style pattern (repeatable)')
    scan_options.add_argument('--exclude-from', action='append', metavar='FILE', help='file with one pattern per line')
    scan_options.add_argument('--skip-technical', action='store_true', help='skip .git, node_modules, __pycache__, ...')
    scan_options.add_argument('--levels', type=int, default=0, help='levels to map (default: all)')
    scan_options.add_argument('--strict', action='store_true', help='exit code 5 if some items could not be read')

    root = argparse.ArgumentParser(prog='mapper-cli', description='Mapper command line: map, export, snapshot and compare folders.',
                                   epilog='Exit codes: 0 ok, 1 differences found (diff), 2 usage, 3 invalid input, '
                                          '4 read/write error, 5 unreadable items (--strict), 130 interrupted.')
    root.add_argument('--version', action='version', version=f'mapper-cli {VERSION}')
    commands = root.add_subparsers(dest='command', required=True, metavar='COMMAND')

    p = commands.add_parser('scan', parents=[common, scan_options], help='map a folder and print a JSON summary')
    p.add_argument('folder')
    p.add_argument('--pretty', action='store_true', help='indented JSON')
    p.set_defaults(run=cmd_scan)

    p = commands.add_parser('export', parents=[common, scan_options], help='map a folder and export it')
    p.add_argument('folder')
    p.add_argument('-f', '--format', choices=export.FORMATS, default='txt')
    p.add_argument('-o', '--out', metavar='FILE', help='output file (default: stdout)')
    p.add_argument('--subtree', metavar='RELATIVE', help='export only this folder (path relative to FOLDER)')
    p.add_argument('--hide-paths', action='store_true', help='no absolute paths in the output')
    p.add_argument('--no-metadata', action='store_true', help='no sizes, dates and attributes')
    p.set_defaults(run=cmd_export)

    p = commands.add_parser('snapshot', parents=[common, scan_options], help='save the state of a folder')
    p.add_argument('folder')
    p.add_argument('-o', '--out', metavar='FILE', help='snapshot file (default: stdout)')
    p.add_argument('--hashes', action='store_true', help='add SHA-256 of every file (reads every file)')
    p.add_argument('--hide-paths', action='store_true', help='no absolute paths in the snapshot')
    p.set_defaults(run=cmd_snapshot)

    p = commands.add_parser('diff', parents=[common, scan_options],
                            help='compare a snapshot with another snapshot or with a folder as it is now')
    p.add_argument('before', help='snapshot file')
    p.add_argument('after', help='snapshot file or folder')
    p.add_argument('-f', '--format', choices=diff.FORMATS, default='json')
    p.add_argument('-o', '--out', metavar='FILE', help='output file (default: stdout)')
    p.add_argument('--hide-paths', action='store_true', help='no absolute paths in the output')
    p.set_defaults(run=cmd_diff)

    p = commands.add_parser('validate', parents=[common], help='check that a snapshot file is valid')
    p.add_argument('file')
    p.set_defaults(run=cmd_validate)
    return root


def main(argv=None):
    # Risultati sempre in UTF-8, anche se reindirizzati / Results always in UTF-8, also when redirected
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    args = parser().parse_args(argv)
    log = Log(args.quiet, args.verbose, args.log_json)
    try:
        return args.run(args, log)
    except CliError as exc:
        log.error('failed', str(exc), code=exc.code)
        return exc.code
    except KeyboardInterrupt:
        log.error('interrupted', 'interrupted', code=INTERRUPTED)
        return INTERRUPTED
    except OSError as exc:
        log.error('io_error', f'{exc.strerror or exc}', code=IO_ERROR)
        return IO_ERROR


if __name__ == '__main__':
    sys.exit(main())
