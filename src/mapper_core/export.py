"""
Esportazione della mappa: TXT (formato 1.5), Markdown, JSON (schema versionato), CSV.
Map export: TXT (1.5 format), Markdown, JSON (versioned schema), CSV.

Ogni formato è un generatore di righe: l'anteprima legge solo le prime, il salvataggio scrive in streaming
su un file temporaneo e poi lo sostituisce in modo atomico (anche oltre 260 caratteri).
Each format is a line generator: the preview reads only the first lines, saving streams to a temporary
file and then replaces the target atomically (also beyond 260 characters).
"""
import csv
import io
import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .model import DIR, FILE, KIND_NAMES, NO_EXTENSION
from .paths import extended, normalize

FORMATS = ('txt', 'md', 'json', 'csv')
SUFFIXES = {'txt': '.txt', 'md': '.md', 'json': '.json', 'csv': '.csv'}
SCHEMA_NAME, SCHEMA_VERSION = 'mapper-tree', 1
CSV_COLUMNS = ('path', 'name', 'type', 'depth', 'extension', 'size', 'modified', 'attributes')
# Attributi di Windows esportati / Exported Windows attributes
ATTRIBUTES = ((0x1, 'readonly', 'R'), (0x2, 'hidden', 'H'), (0x4, 'system', 'S'), (0x20, 'archive', 'A'),
              (0x400, 'reparse_point', 'L'), (0x800, 'compressed', 'C'), (0x1000, 'offline', 'O'),
              (0x4000, 'encrypted', 'E'))
REDACTED = None


@dataclass
class ExportOptions:
    """
    subtree: indice della cartella da esportare (-1 = tutta la mappa); redact: nessun percorso assoluto;
    metadata: dimensioni, date e attributi; generated: data di generazione (UTC, per test riproducibili).
    subtree: folder index to export (-1 = whole map); redact: no absolute path; metadata: sizes, dates and
    attributes; generated: generation time (UTC, for reproducible tests).
    """
    subtree: int = -1
    redact: bool = False
    metadata: bool = True
    generator: str = 'Mapper'
    version: str = ''
    generated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ── Aiuti / Helpers ─────────────────────────────────────────────────────
def iso(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def human_size(size):
    value = float(size)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if value < 1024 or unit == 'TB':
            return f'{int(value)} {unit}' if unit == 'B' else f'{value:.1f} {unit}'
        value /= 1024


def attribute_names(value):
    return [name for bit, name, _ in ATTRIBUTES if value & bit]


def attribute_letters(value):
    return ''.join(letter for bit, _, letter in ATTRIBUTES if value & bit)


def csv_safe(text):
    """
    Anti formula injection: Excel/LibreOffice eseguono celle che iniziano con = + - @ tab o a capo.
    Formula-injection guard: spreadsheet apps run cells starting with = + - @ tab or carriage return.
    """
    return "'" + text if text[:1] in ('=', '+', '-', '@', '\t', '\r') else text


def md_text(text):
    """Testo sicuro in Markdown (tabelle ed elenchi) / Markdown-safe text (tables and lists)."""
    return re.sub(r'([\\`*_{}\[\]<>|#])', r'\\\1', text)


def md_code(text):
    """Testo come codice inline, senza escape / Text as inline code, no escaping needed."""
    longest = max((len(run) for run in re.findall('`+', text)), default=0)
    ticks = '`' * (longest + 1)
    pad = ' ' if text.startswith('`') or text.endswith('`') else ''
    return f'{ticks}{pad}{text}{pad}{ticks}'


class _Scope:
    """Elementi, percorsi e totali della parte esportata / Items, paths and totals of the exported part."""

    def __init__(self, tree, options):
        self.tree, self.options = tree, options
        self.index = options.subtree
        self.start, self.end, self.base = tree.span(self.index)
        self.path = tree.root if self.index < 0 else tree.dir_path(self.index)
        self.name = (os.path.basename(tree.root.rstrip('\\/')) or tree.root.rstrip('\\/')) if self.index < 0 \
            else tree.names[self.index]
        self._prefix = self.path if self.path.endswith(('\\', '/')) else self.path + os.sep
        kinds, sizes = tree.kinds, tree.sizes
        self.folders = self.files = self.links = self.bytes = 0
        self.extensions = {}
        for i in range(self.start, self.end):
            kind = kinds[i]
            if kind == DIR:
                self.folders += 1
            elif kind == FILE:
                self.files += 1
                ext = tree.extension(i) or NO_EXTENSION
                count, size = self.extensions.get(ext, (0, 0))
                item_size = sizes[i] if tree.metadata else 0
                self.extensions[ext] = (count + 1, size + max(item_size, 0))
                self.bytes += max(item_size, 0)
            else:
                self.links += 1
        self.errors = [e for e in tree.errors if self.contains(e.path)]

    def contains(self, path):
        return os.path.normcase(path).startswith(os.path.normcase(self._prefix)) or \
            os.path.normcase(path) == os.path.normcase(self.path)

    def relative(self, path):
        """Percorso relativo con '/' / Relative path with '/'."""
        if os.path.normcase(path) == os.path.normcase(self.path):
            return ''
        return path[len(self._prefix):].replace('\\', '/')

    def root_path(self):
        return REDACTED if self.options.redact else self.path

    def error_path(self, error):
        return self.relative(error.path) if self.contains(error.path) else REDACTED


def _entry(tree, scope, i, metadata):
    kind = tree.kinds[i]
    entry = dict(path=scope.relative(tree.path(i)), name=tree.names[i], type=KIND_NAMES[kind],
                 depth=tree.levels[i] - scope.base)
    if kind == FILE:
        entry['extension'] = tree.extension(i)
    if metadata:
        if kind == FILE:
            entry['size'] = tree.sizes[i]
        entry['modified'] = iso(tree.mtimes[i]) if tree.mtimes[i] else None
        entry['attributes'] = attribute_names(tree.attributes[i])
    return entry


# ── Formati / Formats ───────────────────────────────────────────────────
def txt_lines(tree, options):
    """Mappa ad albero identica alla 1.5 / Tree map identical to 1.5."""
    return tree.lines(options.subtree)


def json_lines(tree, options):
    scope = _Scope(tree, options)
    metadata = options.metadata and tree.metadata
    header = {
        'format': SCHEMA_NAME,
        'version': SCHEMA_VERSION,
        'generator': {'name': options.generator, 'version': options.version},
        'generated': options.generated.isoformat(timespec='seconds').replace('+00:00', 'Z'),
        'root': {'name': scope.name, 'path': scope.root_path()},
        'options': {'subtree': options.subtree >= 0, 'redacted': options.redact, 'metadata': metadata,
                    'levels': tree.levels_limit, 'excluded_patterns': tree.patterns},
        'summary': {'items': scope.end - scope.start, 'folders': scope.folders, 'files': scope.files,
                    'links': scope.links, 'bytes': scope.bytes if metadata else None,
                    'excluded': tree.excluded if options.subtree < 0 else None, 'errors': len(scope.errors),
                    'complete': not tree.cancelled},
    }
    yield '{'
    for key, value in header.items():
        yield f'  {json.dumps(key)}: {json.dumps(value, ensure_ascii=False)},'
    yield '  "entries": ['
    pending = None
    for i in range(scope.start, scope.end):
        if pending is not None:
            yield pending + ','
        pending = '    ' + json.dumps(_entry(tree, scope, i, metadata), ensure_ascii=False)
    if pending is not None:
        yield pending
    yield '  ],'
    errors = [json.dumps({'path': scope.error_path(e), 'reason': e.reason}, ensure_ascii=False) for e in scope.errors]
    if errors:
        yield '  "errors": ['
        for k, error in enumerate(errors):
            yield '    ' + error + (',' if k < len(errors) - 1 else '')
        yield '  ]'
    else:
        yield '  "errors": []'
    yield '}'


def csv_lines(tree, options):
    scope = _Scope(tree, options)
    metadata = options.metadata and tree.metadata
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator='')

    def row(values):
        buffer.seek(0)
        buffer.truncate()
        writer.writerow(values)
        return buffer.getvalue()
    yield row(CSV_COLUMNS)
    for i in range(scope.start, scope.end):
        kind = tree.kinds[i]
        size = tree.sizes[i] if metadata and kind == FILE else ''
        modified = iso(tree.mtimes[i]) if metadata and tree.mtimes[i] else ''
        attributes = attribute_letters(tree.attributes[i]) if metadata else ''
        yield row((csv_safe(scope.relative(tree.path(i))), csv_safe(tree.names[i]), KIND_NAMES[kind],
                   tree.levels[i] - scope.base, csv_safe(tree.extension(i)), size, modified, attributes))


def md_lines(tree, options):
    scope = _Scope(tree, options)
    metadata = options.metadata and tree.metadata
    # Recinto più lungo di qualsiasi sequenza di ` nei nomi / Fence longer than any ` run in the names
    longest = max((len(run) for i in range(scope.start, scope.end) for run in re.findall('`+', tree.names[i])),
                  default=0)
    fence = '`' * max(3, longest + 1)
    generated = options.generated.strftime('%Y-%m-%d %H:%M UTC')
    yield f'# {md_text(scope.name)}'
    yield ''
    yield '| | |'
    yield '| --- | --- |'
    yield '| Path | ' + ('*hidden*' if options.redact else md_code(scope.path)) + ' |'
    yield f'| Generated | {generated} · {md_text(options.generator)} {md_text(options.version)} |'.replace('  |', ' |')
    yield f'| Content | folders: {scope.folders} · files: {scope.files} · links: {scope.links} |'
    if metadata:
        yield f'| Total size | {human_size(scope.bytes)} |'
    if tree.patterns:
        yield '| Excluded patterns | ' + ', '.join(md_code(p) for p in tree.patterns) + ' |'
    if tree.levels_limit:
        yield f'| Levels | {tree.levels_limit} |'
    if tree.cancelled:
        yield '| Status | incomplete (mapping cancelled) |'
    yield ''
    yield '## Tree'
    yield ''
    yield fence + 'text'
    yield from tree.lines(options.subtree)
    yield fence
    if scope.extensions:
        yield ''
        yield '## File types'
        yield ''
        yield '| Extension | Files | Size |' if metadata else '| Extension | Files |'
        yield '| --- | ---: | ---: |' if metadata else '| --- | ---: |'
        for ext, (count, size) in sorted(scope.extensions.items(), key=lambda e: (-e[1][0], e[0])):
            cells = [md_code(ext), str(count)] + ([human_size(size)] if metadata else [])
            yield '| ' + ' | '.join(cells) + ' |'
    if scope.errors:
        yield ''
        yield '## Not read'
        yield ''
        for error in scope.errors:
            yield f'- {md_code(scope.error_path(error) or "(outside)")}: {error.reason}'


GENERATORS = {'txt': txt_lines, 'md': md_lines, 'json': json_lines, 'csv': csv_lines}


def lines(tree, fmt, options=None):
    """Righe dell'esportazione nel formato scelto / Export lines in the chosen format."""
    if fmt not in GENERATORS:
        raise ValueError(f'unknown format: {fmt}')
    return GENERATORS[fmt](tree, options or ExportOptions())


def text(tree, fmt, options=None):
    return '\n'.join(lines(tree, fmt, options))


def write(tree, fmt, destination, options=None, cancel=None):
    """
    Scrive l'esportazione in modo atomico: file temporaneo nella stessa cartella, poi sostituzione.
    Se annullata o in errore il file di destinazione resta com'era. CSV: UTF-8 con BOM e CRLF (Excel).
    Writes the export atomically: temporary file in the same folder, then replacement.
    When cancelled or failing the destination stays as it was. CSV: UTF-8 with BOM and CRLF (Excel).
    Restituisce True se scritto / Returns True when written.
    """
    target = extended(normalize(destination))
    encoding, newline = ('utf-8-sig', '\r\n') if fmt == 'csv' else ('utf-8', None)
    handle, temp = tempfile.mkstemp(prefix='.mapper-', suffix='.tmp', dir=os.path.dirname(target))
    try:
        with os.fdopen(handle, 'w', encoding=encoding, newline=newline) as out:
            for k, line in enumerate(lines(tree, fmt, options)):
                if cancel is not None and k % 4096 == 0 and cancel.is_set():
                    raise InterruptedError
                out.write(line + '\n')
        os.replace(temp, target)
        return True
    except InterruptedError:
        return False
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
