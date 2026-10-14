"""
Snapshot: lo stato di una cartella (percorsi relativi, tipi, dimensioni, date, hash facoltativi) da confrontare.
Un file snapshot è un export JSON `mapper-tree` v1 con i metadati; il caricamento lo valida in modo rigoroso
perché il file può arrivare da chiunque (manipolato, troncato, enorme).
Snapshot: the state of a folder (relative paths, types, sizes, dates, optional hashes) to compare.
A snapshot file is a `mapper-tree` v1 JSON export with metadata; loading validates it strictly
because the file may come from anyone (tampered, truncated, huge).
"""
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime

from .export import SCHEMA_NAME, SCHEMA_VERSION
from .model import FILE, KIND_NAMES
from .paths import extended, normalize

# Limiti contro file malevoli o non realistici / Limits against hostile or unrealistic files
MAX_BYTES = 1 << 30
MAX_ENTRIES = 5_000_000
MAX_PATH = 32_767
MAX_FALLBACK_BYTES = 64 << 20
TYPES = frozenset(KIND_NAMES)
_HEX64 = re.compile(r'[0-9a-f]{64}')
_BAD_CHARS = re.compile(r'[\x00-\x1f<>:"|?*\\]')


class SnapshotError(Exception):
    """Snapshot non valido: key = chiave di traduzione, detail = dove / Invalid snapshot: key and where."""

    def __init__(self, key, detail=''):
        super().__init__(f'{key}: {detail}' if detail else key)
        self.key, self.detail = key, detail


@dataclass(slots=True)
class Item:
    path: str
    type: str
    size: int
    mtime: float
    sha256: str


class Snapshot:
    """
    items: {chiave senza maiuscole: Item}; i percorsi usano '/' e sono relativi alla radice.
    items: {case-folded key: Item}; paths use '/' and are relative to the root.
    """

    def __init__(self, name, root=None, generated=None, source='file'):
        self.name, self.root, self.generated, self.source = name, root, generated, source
        self.items = {}
        self.complete = True

    def __len__(self):
        return len(self.items)

    @property
    def has_hashes(self):
        return any(item.sha256 for item in self.items.values())

    def add(self, item, where=''):
        key = item.path.casefold()
        if key in self.items:
            raise SnapshotError('snapshot_duplicate', where or item.path)
        self.items[key] = item

    @classmethod
    def from_tree(cls, tree):
        """Stato attuale da una scansione / Current state from a scan."""
        snapshot = cls(os.path.basename(tree.root.rstrip('\\/')) or tree.root, tree.root, None, 'scan')
        snapshot.complete = not tree.cancelled
        prefix = len(tree.root if tree.root.endswith(('\\', '/')) else tree.root + os.sep)
        for i in range(len(tree)):
            kind = tree.kinds[i]
            size = tree.sizes[i] if tree.metadata and kind == FILE else -1
            mtime = tree.mtimes[i] if tree.metadata else 0.0
            path = tree.path(i)[prefix:].replace('\\', '/')
            snapshot.items[path.casefold()] = Item(path, KIND_NAMES[kind], size, mtime, None)
        return snapshot


# ── Validazione / Validation ────────────────────────────────────────────
def _reject_constant(value):
    raise ValueError(f'not allowed: {value}')


def _loads(text):
    """JSON senza NaN/Infinity / JSON without NaN/Infinity."""
    return json.loads(text, parse_constant=_reject_constant)


def _parse_time(value, where):
    if value is None:
        return 0.0
    if not isinstance(value, str) or len(value) > 40:
        raise SnapshotError('snapshot_invalid', where)
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
    except ValueError:
        raise SnapshotError('snapshot_invalid', where) from None


def _valid_path(path):
    """Relativo, con '/', senza '..', unità, nomi vuoti o caratteri vietati / Relative, '/', no '..'."""
    if not isinstance(path, str) or not path or len(path) > MAX_PATH:
        return False
    if path.startswith('/') or _BAD_CHARS.search(path):
        return False
    return all(part not in ('', '.', '..') and not part.endswith((' ', '.')) for part in path.split('/'))


def _item(entry, where):
    if not isinstance(entry, dict):
        raise SnapshotError('snapshot_invalid', where)
    path, kind = entry.get('path'), entry.get('type')
    if not _valid_path(path) or kind not in TYPES:
        raise SnapshotError('snapshot_invalid', where)
    size = entry.get('size', -1)
    if size is None:
        size = -1
    if isinstance(size, bool) or not isinstance(size, int) or size < -1 or size > 1 << 62:
        raise SnapshotError('snapshot_invalid', where)
    sha = entry.get('sha256')
    if sha is not None and (not isinstance(sha, str) or not _HEX64.fullmatch(sha)):
        raise SnapshotError('snapshot_invalid', where)
    return Item(path, kind, size, _parse_time(entry.get('modified'), where), sha)


def _header(snapshot_data, where='header'):
    if not isinstance(snapshot_data, dict) or snapshot_data.get('format') != SCHEMA_NAME:
        raise SnapshotError('snapshot_not_mapper', where)
    version = snapshot_data.get('version')
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise SnapshotError('snapshot_not_mapper', where)
    if version > SCHEMA_VERSION:
        raise SnapshotError('snapshot_newer', str(version))
    options = snapshot_data.get('options') or {}
    if isinstance(options, dict) and options.get('metadata') is False:
        raise SnapshotError('snapshot_no_metadata')
    root = snapshot_data.get('root') or {}
    if not isinstance(root, dict):
        raise SnapshotError('snapshot_invalid', where)
    name, path = root.get('name'), root.get('path')
    generated = snapshot_data.get('generated')
    summary = snapshot_data.get('summary') or {}
    snapshot = Snapshot(name if isinstance(name, str) else '', path if isinstance(path, str) else None,
                        generated if isinstance(generated, str) else None)
    snapshot.complete = not (isinstance(summary, dict) and summary.get('complete') is False)
    return snapshot


def _load_lines(handle):
    """
    Lettura riga per riga del formato scritto da Mapper (memoria contenuta anche con milioni di voci).
    Restituisce None se il file non ha quella forma. / Line-by-line read of the layout Mapper writes
    (bounded memory even with millions of entries). Returns None if the file does not have that shape.
    """
    header, snapshot, state = {}, None, 'start'
    for number, raw in enumerate(handle, 1):
        line = raw.strip()
        if state == 'start':
            if line != '{':
                return None
            state = 'header'
        elif state == 'header':
            if line == '"entries": [':
                snapshot, state = _header(header), 'entries'
                continue
            match = re.fullmatch(r'"([a-z_]+)": (.*),', line)
            if not match:
                return None
            header[match.group(1)] = _loads(match.group(2))
        elif state == 'entries':
            if line in (']', '],'):
                state = 'tail'
                continue
            if len(snapshot.items) >= MAX_ENTRIES:
                raise SnapshotError('snapshot_too_large')
            snapshot.add(_item(_loads(line[:-1] if line.endswith(',') else line), f'line {number}'), f'line {number}')
    return snapshot if state == 'tail' else None


def load(path):
    """
    Carica e valida un file snapshot. Errori: SnapshotError con chiave di traduzione.
    Loads and validates a snapshot file. Errors: SnapshotError with a translation key.
    """
    target = extended(normalize(path))
    try:
        size = os.path.getsize(target)
        if size > MAX_BYTES:
            raise SnapshotError('snapshot_too_large')
        with open(target, encoding='utf-8-sig') as handle:
            snapshot = _load_lines(handle)
            if snapshot is not None:
                return snapshot
            # Forma diversa (es. riformattato a mano): JSON completo, ma solo se piccolo
            # Different layout (e.g. reformatted by hand): whole JSON, only if small
            if size > MAX_FALLBACK_BYTES:
                raise SnapshotError('snapshot_invalid', 'layout')
            handle.seek(0)
            data = _loads(handle.read())
    except SnapshotError:
        raise
    except (ValueError, RecursionError, UnicodeDecodeError):
        raise SnapshotError('snapshot_invalid', 'json') from None
    except OSError as exc:
        raise SnapshotError('snapshot_unreadable', exc.strerror or '') from None
    snapshot = _header(data)
    entries = data.get('entries')
    if not isinstance(entries, list):
        raise SnapshotError('snapshot_invalid', 'entries')
    if len(entries) > MAX_ENTRIES:
        raise SnapshotError('snapshot_too_large')
    for number, entry in enumerate(entries):
        snapshot.add(_item(entry, f'entry {number + 1}'), f'entry {number + 1}')
    return snapshot
