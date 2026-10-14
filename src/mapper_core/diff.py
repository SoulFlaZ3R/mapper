"""
Confronto tra due snapshot: aggiunti, rimossi, modificati, rinominati (probabili).
Comparison between two snapshots: added, removed, modified, (probably) renamed.

Regole / Rules:
- Contenuto modificato solo con una prova: dimensione diversa o SHA-256 diverso. Date diverse senza prova
  = modifica dei metadati ("metadata"), mai "content". verified=True quando il contenuto è stato confrontato
  con gli hash.
- Le date delle cartelle non contano (cambiano a ogni modifica dei figli, già elencata).
- Rinomina/spostamento probabile solo se la corrispondenza è unica:
    folder:    cartella rimossa e aggiunta con lo stesso contenuto (percorsi relativi, tipi, dimensioni)
    hash:      file con lo stesso SHA-256 (contenuto identico, verified=True)
    size_date: file con stessa dimensione (> 0), stessa data e stessa estensione
- Content modified only with evidence: different size or different SHA-256. Different dates without evidence
  = metadata change, never "content". verified=True when content was compared through hashes.
- Folder dates are ignored (they change with every child change, which is listed anyway).
- A probable rename/move is reported only for a unique match (criteria above).
"""
import csv
import io
import json
import os
from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .export import csv_safe, human_size, iso, md_code, md_text, write_lines

SCHEMA_NAME, SCHEMA_VERSION = 'mapper-diff', 1
KINDS = ('added', 'removed', 'modified', 'renamed')
CSV_COLUMNS = ('change', 'path', 'old_path', 'type', 'detail', 'verified', 'old_size', 'new_size',
               'old_modified', 'new_modified')
# Tolleranza sulle date: precisione al millesimo degli snapshot / Date tolerance: snapshot millisecond precision
MTIME_TOLERANCE = 0.002


@dataclass(slots=True)
class Change:
    kind: str
    path: str
    type: str
    old_path: str = ''
    old_size: int = -1
    new_size: int = -1
    old_mtime: float = 0.0
    new_mtime: float = 0.0
    detail: str = ''
    verified: bool = False


@dataclass
class DiffResult:
    old_name: str
    new_name: str
    old_root: str = None
    new_root: str = None
    old_generated: str = None
    new_generated: str = None
    changes: list = field(default_factory=list)
    unchanged: int = 0
    hashes_used: bool = False
    complete: bool = True

    def count(self, kind, detail=None):
        return sum(1 for c in self.changes if c.kind == kind and (detail is None or c.detail == detail))

    def summary(self):
        return {kind: self.count(kind) for kind in KINDS} | {
            'unchanged': self.unchanged, 'content': self.count('modified', 'content'),
            'metadata': self.count('modified', 'metadata')}


def _extension(path):
    return os.path.splitext(path.rsplit('/', 1)[-1])[1].lower()


def _descendants(keys, prefix):
    """Chiavi che iniziano con prefix (lista ordinata) / Keys starting with prefix (sorted list)."""
    start = bisect_left(keys, prefix)
    end = bisect_left(keys, prefix + '\U0010ffff')
    return keys[start:end]


def _top_level(keys, items):
    """Cartelle il cui genitore non è nello stesso insieme / Folders whose parent is not in the same set."""
    present = set(keys)
    return [k for k in keys if items[k].type == 'dir' and k.rpartition('/')[0] not in present]


def _signature(folder, keys, items, use_hashes):
    prefix = folder + '/'
    inner = _descendants(keys, prefix)
    if not any(items[k].type == 'file' for k in inner):
        return None
    return tuple((k[len(prefix):], items[k].type, items[k].size, items[k].sha256 if use_hashes else None)
                 for k in inner)


def _unique_pairs(left, right):
    """Coppie per chiave presente una sola volta per lato / Pairs for keys present once on each side."""
    return [(left[key][0], right[key][0]) for key in left.keys() & right.keys()
            if len(left[key]) == 1 and len(right[key]) == 1]


def compare(old, new, verify=None, tolerance=MTIME_TOLERANCE):
    """
    old, new: Snapshot. verify(percorso relativo) -> sha256 del file attuale, usato solo quando serve
    (old ha l'hash, stessa dimensione, data diversa) per non rileggere tutto il disco.
    old, new: Snapshot. verify(relative path) -> sha256 of the current file, used only when needed
    (old has a hash, same size, different date) so the disk is not read in full.
    """
    result = DiffResult(old.name, new.name, old.root, new.root, old.generated, new.generated)
    result.complete = old.complete and new.complete
    a_items, b_items = old.items, new.items
    use_hashes = old.has_hashes and new.has_hashes
    changes = result.changes
    for key in a_items.keys() & b_items.keys():
        a, b = a_items[key], b_items[key]
        if a.type != b.type:
            changes.append(Change('modified', b.path, b.type, a.path, a.size, b.size, a.mtime, b.mtime, 'type'))
            continue
        if a.type != 'file':
            result.unchanged += 1
            continue
        dates_differ = bool(a.mtime and b.mtime) and abs(a.mtime - b.mtime) > tolerance
        content, verified = None, False
        if a.sha256 and b.sha256:
            content, verified = a.sha256 != b.sha256, True
        elif a.size >= 0 and b.size >= 0 and a.size != b.size:
            content = True
        elif verify is not None and a.sha256 and dates_differ:
            current = verify(b.path)
            if current:
                content, verified = current != a.sha256, True
                result.hashes_used = True
        if content:
            changes.append(Change('modified', b.path, 'file', a.path, a.size, b.size, a.mtime, b.mtime, 'content', verified))
        elif dates_differ:
            changes.append(Change('modified', b.path, 'file', a.path, a.size, b.size, a.mtime, b.mtime, 'metadata', verified))
        else:
            result.unchanged += 1
    result.hashes_used = result.hashes_used or use_hashes
    removed = sorted(a_items.keys() - b_items.keys())
    added = sorted(b_items.keys() - a_items.keys())
    gone, born = set(removed), set(added)
    # Cartelle spostate o rinominate con tutto il loro contenuto / Folders moved or renamed with all their content
    left, right = defaultdict(list), defaultdict(list)
    for key in _top_level(removed, a_items):
        signature = _signature(key, removed, a_items, use_hashes)
        if signature is not None:
            left[signature].append(key)
    for key in _top_level(added, b_items):
        signature = _signature(key, added, b_items, use_hashes)
        if signature is not None:
            right[signature].append(key)
    for old_key, new_key in _unique_pairs(left, right):
        a, b = a_items[old_key], b_items[new_key]
        changes.append(Change('renamed', b.path, 'dir', a.path, detail='folder', verified=use_hashes))
        for key in [old_key] + _descendants(removed, old_key + '/'):
            gone.discard(key)
        for key in [new_key] + _descendants(added, new_key + '/'):
            born.discard(key)
    # File rinominati o spostati / Files renamed or moved
    left, right = defaultdict(list), defaultdict(list)
    for side, keys, items in ((left, gone, a_items), (right, born, b_items)):
        for key in keys:
            item = items[key]
            if item.type != 'file':
                continue
            if use_hashes and item.sha256:
                side[('hash', item.sha256)].append(key)
            elif item.size > 0 and item.mtime:
                side[('size_date', item.size, round(item.mtime, 3), _extension(item.path))].append(key)
    for old_key, new_key in _unique_pairs(left, right):
        a, b = a_items[old_key], b_items[new_key]
        by_hash = bool(use_hashes and a.sha256)
        changes.append(Change('renamed', b.path, 'file', a.path, a.size, b.size, a.mtime, b.mtime,
                              'hash' if by_hash else 'size_date', by_hash))
        gone.discard(old_key)
        born.discard(new_key)
    for key in gone:
        a = a_items[key]
        changes.append(Change('removed', a.path, a.type, a.path, a.size, -1, a.mtime, 0.0))
    for key in born:
        b = b_items[key]
        changes.append(Change('added', b.path, b.type, '', -1, b.size, 0.0, b.mtime))
    changes.sort(key=lambda c: (c.path.casefold(), KINDS.index(c.kind)))
    return result


# ── Esportazione del confronto / Comparison export ──────────────────────
@dataclass
class DiffExportOptions:
    redact: bool = False
    generator: str = 'Mapper'
    version: str = ''
    generated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def _when(timestamp):
    return iso(timestamp) if timestamp else None


def _change_dict(change):
    entry = {'change': change.kind, 'path': change.path, 'type': change.type}
    if change.kind in ('renamed', 'modified') and change.old_path != change.path:
        entry['old_path'] = change.old_path
    if change.detail:
        entry['detail'] = change.detail
    if change.kind in ('modified', 'renamed'):
        entry['verified'] = change.verified
    if change.type == 'file':
        if change.kind != 'added':
            entry['old_size'] = change.old_size
            entry['old_modified'] = _when(change.old_mtime)
        if change.kind != 'removed':
            entry['new_size'] = change.new_size
            entry['new_modified'] = _when(change.new_mtime)
    return entry


def json_lines(result, options):
    header = {
        'format': SCHEMA_NAME,
        'version': SCHEMA_VERSION,
        'generator': {'name': options.generator, 'version': options.version},
        'generated': options.generated.isoformat(timespec='seconds').replace('+00:00', 'Z'),
        'old': {'name': result.old_name, 'path': None if options.redact else result.old_root,
                'generated': result.old_generated},
        'new': {'name': result.new_name, 'path': None if options.redact else result.new_root,
                'generated': result.new_generated},
        'options': {'hashes_used': result.hashes_used, 'mtime_tolerance_s': MTIME_TOLERANCE,
                    'redacted': options.redact},
        'summary': result.summary() | {'complete': result.complete},
    }
    yield '{'
    for key, value in header.items():
        yield f'  {json.dumps(key)}: {json.dumps(value, ensure_ascii=False)},'
    yield '  "changes": ['
    for k, change in enumerate(result.changes):
        yield '    ' + json.dumps(_change_dict(change), ensure_ascii=False) + (',' if k < len(result.changes) - 1 else '')
    yield '  ]'
    yield '}'


def csv_lines(result, options):
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator='')

    def row(values):
        buffer.seek(0)
        buffer.truncate()
        writer.writerow(values)
        return buffer.getvalue()
    yield row(CSV_COLUMNS)
    for change in result.changes:
        file = change.type == 'file'
        yield row((change.kind, csv_safe(change.path), csv_safe(change.old_path if change.old_path != change.path else ''),
                   change.type, change.detail, 'yes' if change.verified else '',
                   change.old_size if file and change.kind != 'added' else '',
                   change.new_size if file and change.kind != 'removed' else '',
                   _when(change.old_mtime) or '', _when(change.new_mtime) or ''))


def md_lines(result, options):
    summary = result.summary()
    yield f'# Comparison: {md_text(result.old_name)} → {md_text(result.new_name)}'
    yield ''
    yield '| | Before | After |'
    yield '| --- | --- | --- |'
    if not options.redact:
        yield f'| Path | {md_code(result.old_root or "")} | {md_code(result.new_root or "")} |'
    yield f'| Snapshot | {md_text(result.old_generated or "current scan")} | {md_text(result.new_generated or "current scan")} |'
    yield ''
    yield (f'Added: {summary["added"]} · removed: {summary["removed"]} · modified: {summary["modified"]} '
           f'(content: {summary["content"]}, dates only: {summary["metadata"]}) · renamed or moved: '
           f'{summary["renamed"]} · unchanged: {summary["unchanged"]}')
    yield ''
    yield ('Content changes are confirmed by a different size or SHA-256 hash; "dates only" means the content was '
           'not proven to change.' + ('' if result.complete else ' **One side is incomplete (mapping cancelled).**'))
    titles = {'added': 'Added', 'removed': 'Removed', 'modified': 'Modified', 'renamed': 'Renamed or moved'}
    for kind in KINDS:
        rows = [c for c in result.changes if c.kind == kind]
        if not rows:
            continue
        yield ''
        yield f'## {titles[kind]} ({len(rows)})'
        yield ''
        if kind == 'renamed':
            yield '| From | To | Evidence |'
            yield '| --- | --- | --- |'
            for c in rows:
                yield f'| {md_code(c.old_path)} | {md_code(c.path)} | {c.detail} |'
        elif kind == 'modified':
            yield '| Path | Change | Size | Modified |'
            yield '| --- | --- | ---: | --- |'
            for c in rows:
                label = {'content': 'content' + (' (hash)' if c.verified else ' (size)'),
                         'metadata': 'dates only' + (' (same hash)' if c.verified else ''), 'type': 'type'}[c.detail]
                size = f'{human_size(c.old_size)} → {human_size(c.new_size)}' if c.type == 'file' and c.old_size >= 0 \
                    and c.new_size >= 0 else ''
                dates = f'{_when(c.old_mtime) or "?"} → {_when(c.new_mtime) or "?"}' if c.type == 'file' else ''
                yield f'| {md_code(c.path)} | {label} | {size} | {dates} |'
        else:
            yield '| Path | Type | Size |'
            yield '| --- | --- | ---: |'
            for c in rows:
                size = c.old_size if kind == 'removed' else c.new_size
                yield f'| {md_code(c.path)} | {c.type} | {human_size(size) if c.type == "file" and size >= 0 else ""} |'


GENERATORS = {'json': json_lines, 'md': md_lines, 'csv': csv_lines}
FORMATS = tuple(GENERATORS)


def lines(result, fmt, options=None):
    if fmt not in GENERATORS:
        raise ValueError(f'unknown format: {fmt}')
    return GENERATORS[fmt](result, options or DiffExportOptions())


def text(result, fmt, options=None):
    return '\n'.join(lines(result, fmt, options))


def write(result, fmt, destination, options=None, cancel=None):
    return write_lines(lines(result, fmt, options), destination, csv_format=fmt == 'csv', cancel=cancel)
