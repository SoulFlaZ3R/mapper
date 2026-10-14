"""
Qt models and async filesystem services; workers never touch Qt objects.
Modelli Qt e servizi asincroni sul filesystem; i worker non toccano oggetti Qt.
La logica sul filesystem vive in mapper_core (senza Qt) / Filesystem logic lives in mapper_core (no Qt).
"""
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
from array import array
from itertools import islice
from pathlib import Path
from PySide6.QtCore import (QAbstractListModel, QFile, QLocale, QModelIndex, QObject, Property,
                            QTimer, Qt, QUrl, Signal, Slot)
from PySide6.QtGui import QDesktopServices, QGuiApplication
from mapper_core import DIR, FILE, diff, export, fsops, scan as scan_tree, snapshot
from mapper_core.filters import Excludes
from mapper_core.model import KIND_NAMES, NO_EXTENSION
from mapper_core.paths import display, extended, normalize

VERSION = '1.5.0'
THEMES = ('light', 'dark', 'blue', 'red', 'system')
LANGUAGES = ('it', 'en', 'de', 'fr', 'es')
PREVIEW_LINES = 1200
# Livelli selezionabili nelle impostazioni (0 = tutti) / Levels selectable in Settings (0 = all)
LEVEL_CHOICES = (0, 1, 2, 3, 4, 5, 6, 8, 10, 15, 20)
MAX_RECENT = 6
# Errori di scansione passati alla finestra di dettaglio / Scan errors passed to the details dialog
MAX_ERRORS_SHOWN = 500

BASE = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))


def data_dir():
    """
    Cartella dati nascosta dell'utente: %APPDATA%/Mapper (niente file accanto all'exe).
    Hidden per-user data folder: %APPDATA%/Mapper (no files next to the exe).
    """
    return Path(os.environ.get('APPDATA') or Path.home()) / 'Mapper'


def config_location():
    """
    Exe: config.json accanto all'exe solo se esiste già (modalità chiavetta), altrimenti %APPDATA%.
    Sorgente: src/config.json.
    Exe: config.json next to the exe only if it already exists (USB mode), otherwise %APPDATA%.
    Source: src/config.json.
    """
    if not getattr(sys, 'frozen', False):
        return BASE / 'config.json'
    portable = Path(sys.executable).parent / 'config.json'
    return portable if portable.is_file() else data_dir() / 'config.json'


CONFIG = config_location()


def resolve(path):
    """
    Percorso reale (link, '..', nomi brevi 8.3 risolti), anche oltre 260 caratteri.
    Real path (links, '..', 8.3 short names resolved), also beyond 260 characters.
    """
    return display(os.path.realpath(extended(normalize(path))))


def inside(path, root):
    """path è root o un suo discendente (confronto Windows) / path is root or below it (Windows rules)."""
    return Path(path).is_relative_to(Path(root))


class UserError(Exception):
    """Errore con messaggio tradotto / Error carrying a translation key."""
    def __init__(self, key):
        super().__init__(key)
        self.key = key


class FileModel(QAbstractListModel):
    """
    Righe visibili = indici nell'albero della scansione: nessuna copia per elemento.
    Visible rows = indices into the scan tree: no per-item copies.
    """
    fields = ('itemName', 'fullPath', 'directory', 'level', 'expanded', 'extension', 'relativePath',
              'parentPath', 'kind', 'size', 'modified')

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = array('i')
        self.tree = None
        self.expanded = frozenset()
        self.searching = False

    def roleNames(self):
        return {Qt.UserRole + i + 1: name.encode() for i, name in enumerate(self.fields)}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    @staticmethod
    def _value(tree, expanded, searching, entry, field):
        if field == 'itemName':
            return tree.names[entry]
        if field == 'fullPath':
            return tree.path(entry)
        if field == 'directory':
            return tree.kinds[entry] == DIR
        if field == 'level':
            return 0 if searching else tree.levels[entry]
        if field == 'expanded':
            return tree.kinds[entry] == DIR and os.path.normcase(tree.dir_path(entry)) in expanded
        if field == 'extension':
            return tree.extension(entry)
        if field == 'relativePath':
            return tree.relative(entry)
        if field == 'parentPath':
            return tree.parent_path(entry)
        if field == 'kind':
            return KIND_NAMES[tree.kinds[entry]]
        if field == 'size':
            return float(tree.size(entry))
        return tree.mtime(entry)

    def data(self, index, role):
        i = role - Qt.UserRole - 1
        if index.isValid() and 0 <= index.row() < len(self.rows) and 0 <= i < len(self.fields):
            return self._value(self.tree, self.expanded, self.searching, self.rows[index.row()], self.fields[i])
        return None

    def item(self, row):
        """Tutti i campi di una riga (test e diagnostica) / All fields of a row (tests, diagnostics)."""
        entry = self.rows[row]
        return {f: self._value(self.tree, self.expanded, self.searching, entry, f) for f in self.fields}

    @Slot(str, result=int)
    def indexOf(self, path):
        entry = self.tree.index_of(path) if self.tree else -1
        if entry < 0:
            return -1
        try:
            return self.rows.index(entry)
        except ValueError:
            return -1

    def replace(self, rows, tree, expanded, searching, reset=False):
        """
        Aggiorna con rimozioni/inserimenti minimi così la vista mantiene scroll e selezione.
        Updates with minimal removals/insertions so the view keeps scroll and selection.
        """
        old, old_tree, old_expanded, old_searching = self.rows, self.tree, self.expanded, self.searching
        if reset or not len(old) or not len(rows) or old_tree is None or tree is None:
            self.beginResetModel()
            self.rows, self.tree, self.expanded, self.searching = rows, tree, expanded, searching
            self.endResetModel()
            return
        same_tree = old_tree is tree
        def same(a, b):
            return a == b if same_tree else old_tree.path(a) == tree.path(b)
        def state(t, exp, search, entry):
            return (self._value(t, exp, search, entry, 'expanded'), self._value(t, exp, search, entry, 'level'))
        n, m = len(old), len(rows)
        head = 0
        while head < min(n, m) and same(old[head], rows[head]):
            head += 1
        tail = 0
        while tail < min(n, m) - head and same(old[n - 1 - tail], rows[m - 1 - tail]):
            tail += 1
        # Righe rimaste al loro posto ma con dati diversi (es. freccia espansa)
        # Rows that kept their place but changed data (e.g. expanded arrow)
        kept = list(range(head)) + [m - 1 - j for j in range(tail)]
        old_rows_of = {k: (k if k < head else n - (m - k)) for k in kept}
        changed = sorted(k for k in kept if state(old_tree, old_expanded, old_searching, old[old_rows_of[k]])
                         != state(tree, expanded, searching, rows[k]))
        if n - tail > head:
            self.beginRemoveRows(QModelIndex(), head, n - tail - 1)
            self.rows = old[:head] + old[n - tail:]
            self.endRemoveRows()
        if m - tail > head:
            self.beginInsertRows(QModelIndex(), head, m - tail - 1)
            self.rows, self.tree, self.expanded, self.searching = rows, tree, expanded, searching
            self.endInsertRows()
        self.rows, self.tree, self.expanded, self.searching = rows, tree, expanded, searching
        if changed:
            self.dataChanged.emit(self.index(changed[0]), self.index(changed[-1]))


class DiffModel(QAbstractListModel):
    """
    Differenze del confronto, filtrate per tipo e testo. Date in ISO UTC, dimensioni in byte (-1 = n/d).
    Comparison changes, filtered by kind and text. Dates in ISO UTC, sizes in bytes (-1 = n/a).
    """
    fields = ('change', 'path', 'oldPath', 'type', 'detail', 'verified', 'oldSize', 'newSize',
              'oldModified', 'newModified')

    def __init__(self, parent=None):
        super().__init__(parent)
        self.changes, self.rows = [], []

    def roleNames(self):
        return {Qt.UserRole + i + 1: name.encode() for i, name in enumerate(self.fields)}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    @staticmethod
    def _value(change, field):
        if field == 'change':
            return change.kind
        if field == 'path':
            return change.path
        if field == 'oldPath':
            return change.old_path if change.old_path != change.path else ''
        if field == 'type':
            return change.type
        if field == 'detail':
            return change.detail
        if field == 'verified':
            return change.verified
        if field == 'oldSize':
            return float(change.old_size)
        if field == 'newSize':
            return float(change.new_size)
        if field == 'oldModified':
            return export.iso(change.old_mtime) if change.old_mtime else ''
        return export.iso(change.new_mtime) if change.new_mtime else ''

    def data(self, index, role):
        i = role - Qt.UserRole - 1
        if index.isValid() and 0 <= index.row() < len(self.rows) and 0 <= i < len(self.fields):
            return self._value(self.rows[index.row()], self.fields[i])
        return None

    def item(self, row):
        return {f: self._value(self.rows[row], f) for f in self.fields}

    def load(self, changes):
        self.changes = changes
        self.apply('', '')

    def apply(self, kind, query):
        query = query.casefold().strip()
        self.beginResetModel()
        self.rows = [c for c in self.changes if (not kind or c.kind == kind) and
                     (not query or query in c.path.casefold() or query in c.old_path.casefold())]
        self.endResetModel()


class MapperBackend(QObject):
    changed = Signal()
    translationsChanged = Signal()
    extensionsChanged = Signal()
    recentChanged = Signal()
    revealed = Signal(int)
    comparisonReady = Signal()

    def __init__(self, config_path=None):
        super().__init__()
        self.config_path = Path(config_path or CONFIG)
        self.model = FileModel(self)
        self.diff_model = DiffModel(self)
        self._diff = None
        self._state = dict(path='', busy=False, progress=-1.0, status='', error=False, scanned=False,
                           total=0, folders=0, files=0, links=0, errors=0, found=0, shown=0, query='',
                           extension='', theme='light', language='en', reducedMotion=False, clipboard='',
                           clipboardMode='', version=VERSION, cancellable=True, rootName='',
                           previewLimit=PREVIEW_LINES, excludeTechnical=False, excludePatterns='', maxLevels=0,
                           excluded=0, truncated=0, diff={})
        try:
            prefs = json.loads(self.config_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            prefs = {}
        if not isinstance(prefs, dict):
            prefs = {}
        language = prefs.get('language', QLocale.system().name()[:2])
        theme = prefs.get('theme', 'light')
        recent = prefs.get('recent', [])
        self._recent = [p for p in recent if isinstance(p, str)][:MAX_RECENT] if isinstance(recent, list) else []
        self._state.update(language=language if language in LANGUAGES else 'en',
                           theme=theme if theme in THEMES else 'light',
                           reducedMotion=bool(prefs.get('reducedMotion', False)))
        # Opzioni di scansione: valori non validi tornano ai predefiniti / Scan options: invalid values fall back
        patterns = prefs.get('excludePatterns', '')
        levels = prefs.get('maxLevels', 0)
        self._state.update(excludeTechnical=prefs.get('excludeTechnical') is True,
                           excludePatterns=patterns if isinstance(patterns, str) and self._valid_patterns(patterns) else '',
                           maxLevels=levels if levels in LEVEL_CHOICES and not isinstance(levels, bool) else 0)
        self._translations = self._load_translations()
        self._tree = None
        self._extensions = []
        # Cartelle aperte come percorsi normcase: sopravvivono a una nuova scansione
        # Open folders as normcase paths: they survive a re-scan
        self._expanded = set()
        self._scanned_root = None
        self._status_source = None
        self._pending_reveal = None
        self._clipboard = None
        self._note = None
        self._cancelled_key = 'scan_cancelled'
        self._cancel = threading.Event()
        self._queue = queue.Queue()
        self._closed = False
        self._filter_revision = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._drain)
        self._timer.start(40)
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.timeout.connect(self._filter)

    # ── Proprietà esposte a QML / Properties exposed to QML ─────────────
    @Property('QVariantMap', notify=changed)
    def state(self):
        return self._state

    @Property('QVariantMap', notify=translationsChanged)
    def translations(self):
        return self._translations

    @Property('QVariantList', notify=extensionsChanged)
    def extensions(self):
        return self._extensions

    @Property('QStringList', notify=recentChanged)
    def recent(self):
        return self._recent

    @Slot(result=str)
    def preview(self):
        return '\n'.join(islice(self._tree.lines(), PREVIEW_LINES)) if self._tree else ''

    @Slot(result=int)
    def lineCount(self):
        return self._tree.line_count() if self._tree else 0

    @Slot(result='QVariantList')
    def scanErrors(self):
        """Elementi non letti nell'ultima scansione / Items not read in the latest scan."""
        if not self._tree:
            return []
        return [dict(path=e.path, reason=e.reason) for e in self._tree.errors[:MAX_ERRORS_SHOWN]]

    def map_text(self):
        """Mappa completa dell'ultima scansione / Full map of the latest scan."""
        return '\n'.join(self._tree.lines()) if self._tree else ''

    def _export_options(self, subtree, redact, metadata):
        """Opzioni di export; subtree = percorso di una cartella o '' / Export options; subtree = folder path or ''."""
        index = self._tree.index_of(subtree) if subtree and self._tree else -1
        if index >= 0 and self._tree.kinds[index] != DIR:
            index = -1
        return export.ExportOptions(subtree=index, redact=bool(redact), metadata=bool(metadata), version=VERSION)

    @Slot(str, result=bool)
    def isFolder(self, path):
        """Cartella presente nell'ultima mappa (menu contestuale) / Folder in the latest map (context menu)."""
        index = self._tree.index_of(path) if path and self._tree else -1
        return index >= 0 and self._tree.kinds[index] == DIR

    @Slot(str, str, bool, bool, result='QVariantMap')
    def exportPreview(self, fmt, subtree, redact, metadata):
        """Prime righe dell'esportazione / First lines of the export."""
        if not self._tree or fmt not in export.FORMATS:
            return dict(text='', partial=False, lines=0)
        rows = list(islice(export.lines(self._tree, fmt, self._export_options(subtree, redact, metadata)),
                           PREVIEW_LINES + 1))
        partial = len(rows) > PREVIEW_LINES
        return dict(text='\n'.join(rows[:PREVIEW_LINES]), partial=partial, lines=min(len(rows), PREVIEW_LINES))

    @Slot(str, str, bool, bool)
    def copyExport(self, fmt, subtree, redact, metadata):
        if self._tree and fmt in export.FORMATS:
            options = self._export_options(subtree, redact, metadata)
            QGuiApplication.clipboard().setText(export.text(self._tree, fmt, options))
            self._status('map_copied')

    @Slot(str, str, str, bool, bool)
    def saveExport(self, url, fmt, subtree, redact, metadata):
        """
        Salva l'esportazione nel formato scelto, in modo atomico, in un thread.
        Saves the export in the chosen format, atomically, in a thread.
        """
        if not self._state['scanned'] or self._state['busy'] or not self._tree or fmt not in export.FORMATS:
            return
        destination = QUrl(url).toLocalFile() if QUrl(url).isLocalFile() else url
        tree, options = self._tree, self._export_options(subtree, redact, metadata)
        def job(cancel):
            export.write(tree, fmt, destination, options, cancel)
            return destination
        self._work(job, lambda path: self._status('saved_to', path=path))

    # ── Snapshot e confronto / Snapshots and comparison ─────────────────
    @Slot(str, bool)
    def saveSnapshot(self, url, hashes):
        """
        Snapshot = export JSON completo con metadati; hashes legge ogni file (lento, annullabile con Esc).
        Snapshot = full JSON export with metadata; hashes reads every file (slow, Esc cancels).
        """
        if not self._state['scanned'] or self._state['busy'] or not self._tree:
            return
        destination = QUrl(url).toLocalFile() if QUrl(url).isLocalFile() else url
        tree = self._tree
        options = export.ExportOptions(metadata=True, hashes=bool(hashes), version=VERSION)
        def job(cancel):
            export.write(tree, 'json', destination, options, cancel)
            return destination
        self._status('hashing' if hashes else 'working')
        self._work(job, lambda path: self._status('snapshot_saved', path=path), cancelled='operation_cancelled')

    def _load_snapshot(self, url):
        path = QUrl(url).toLocalFile() if QUrl(url).isLocalFile() else url
        try:
            return snapshot.load(path)
        except snapshot.SnapshotError as exc:
            raise UserError(exc.key) from None

    def _show_diff(self, result, live):
        self._diff = (result, live)
        self.diff_model.load(result.changes)
        self._set(diff=dict(result.summary(), open=True, live=live, oldName=result.old_name,
                            newName=result.new_name, oldDate=result.old_generated or '',
                            newDate=result.new_generated or '', complete=result.complete,
                            hashes=result.hashes_used, total=len(result.changes)))
        self._status('compare_done', count=len(result.changes))
        self.comparisonReady.emit()

    @Slot(str)
    def compareWithSnapshot(self, url):
        """Snapshot salvato (prima) contro la mappa attuale (dopo) / Saved snapshot (before) vs current map (after)."""
        if not self._state['scanned'] or self._state['busy'] or not self._tree:
            return
        tree, root = self._tree, self._tree.root
        def verify(relative):
            return export.sha256_file(os.path.join(root, relative.replace('/', os.sep)))
        def job(cancel):
            before = self._load_snapshot(url)
            return diff.compare(before, snapshot.Snapshot.from_tree(tree), verify=verify)
        self._status('comparing')
        self._work(job, lambda result: self._show_diff(result, True), cancelled='operation_cancelled')

    @Slot(str, str)
    def compareSnapshots(self, before_url, after_url):
        if self._state['busy']:
            return
        def job(cancel):
            return diff.compare(self._load_snapshot(before_url), self._load_snapshot(after_url))
        self._status('comparing')
        self._work(job, lambda result: self._show_diff(result, False), cancelled='operation_cancelled')

    @Slot(str, str)
    def setDiffFilter(self, kind, query):
        self.diff_model.apply(kind if kind in diff.KINDS else '', query)

    @Slot(str, str, bool)
    def exportDiff(self, url, fmt, redact):
        if not self._diff or self._state['busy'] or fmt not in diff.FORMATS:
            return
        destination = QUrl(url).toLocalFile() if QUrl(url).isLocalFile() else url
        result = self._diff[0]
        options = diff.DiffExportOptions(redact=bool(redact), version=VERSION)
        def job(cancel):
            diff.write(result, fmt, destination, options, cancel)
            return destination
        self._work(job, lambda path: self._status('saved_to', path=path), cancelled='operation_cancelled')

    @Slot(str)
    def revealChange(self, relative):
        """Mostra nell'albero un elemento del confronto con la mappa attuale / Shows a compared item in the tree."""
        if not self._diff or not self._diff[1] or not self._tree:
            return
        path = os.path.join(self._tree.root, relative.replace('/', os.sep))
        if self._tree.index_of(path) >= 0:
            self.reveal(path)

    @Slot()
    def closeDiff(self):
        self._diff = None
        self.diff_model.load([])
        self._set(diff={})

    @Slot(bool, str, int, result=bool)
    def setScanOptions(self, technical, patterns, levels):
        """
        Esclusioni e livelli; salvati e applicati subito con una nuova mappatura.
        Exclusions and levels; saved and applied right away with a new mapping.
        """
        patterns = patterns.replace('\r', '')
        if not self._valid_patterns(patterns):
            self._status('error_pattern', error=True)
            return False
        levels = levels if levels in LEVEL_CHOICES else 0
        changed = (bool(technical), patterns, levels) != (self._state['excludeTechnical'],
                                                          self._state['excludePatterns'], self._state['maxLevels'])
        self._set(excludeTechnical=bool(technical), excludePatterns=patterns, maxLevels=levels)
        self._save_config()
        if changed and self._state['scanned'] and not self._state['busy']:
            self.scan()
        return True

    @staticmethod
    def _valid_patterns(patterns):
        try:
            Excludes.from_text(patterns)
            return True
        except re.error:
            return False

    # ── Stato, traduzioni, errori / State, translations, errors ─────────
    def _load_translations(self):
        data = json.loads((BASE / 'Languages' / 'en.json').read_text(encoding='utf-8'))
        data.update(json.loads((BASE / 'Languages' / (self._state['language'] + '.json')).read_text(encoding='utf-8')))
        return data

    def _set(self, **values):
        self._state.update(values)
        self.changed.emit()

    def _status(self, key, error=False, parts=(), **values):
        # Conserva la chiave per ritradurre al cambio lingua / Keep the key to re-translate on language change
        # parts: altre (chiave, valori) aggiunte dopo ' · ' / more (key, values) appended after ' · '
        self._status_source = (key, values, error, parts)
        text = ' · '.join([self._translations[key].format(**values)] +
                          [self._translations[k].format(**v) for k, v in parts])
        self._set(status=text, error=error)

    @staticmethod
    def _part(key, **values):
        return key, values

    def _error(self, exc):
        if isinstance(exc, UserError):
            self._status(exc.key, error=True)
        else:
            self._status('error_operation', error=True, details=str(exc))

    def _save_config(self):
        prefs = dict(theme=self._state['theme'], language=self._state['language'],
                     reducedMotion=self._state['reducedMotion'], recent=self._recent,
                     excludeTechnical=self._state['excludeTechnical'], excludePatterns=self._state['excludePatterns'],
                     maxLevels=self._state['maxLevels'])
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.config_path.write_text(json.dumps(prefs, indent=2, ensure_ascii=False), encoding='utf-8')
        except OSError as exc:
            self._error(exc)

    # ── Lavori in background / Background jobs ──────────────────────────
    def _work(self, job, done, cancellable=True, cancelled='scan_cancelled'):
        if self._state['busy']:
            return False
        self._cancelled_key = cancelled
        self._cancel = threading.Event()
        cancel = self._cancel
        self._set(busy=True, error=False, progress=-1.0, cancellable=cancellable)
        def run():
            try:
                result = job(cancel)
                self._queue.put(('done', (done, result, cancel.is_set())))
            except Exception as exc:
                self._queue.put(('error', exc))
        threading.Thread(target=run, daemon=True).start()
        return True

    def _drain(self):
        for _ in range(32):
            try:
                kind, payload = self._queue.get_nowait()
            except queue.Empty:
                break
            if kind == 'found':
                if self._state['busy']:
                    self._set(found=payload)
                    self._status('scanning_found', count=payload)
            elif kind == 'filter':
                revision, rows, tree, expanded, searching, reset = payload
                if revision == self._filter_revision:
                    self.model.replace(rows, tree, expanded, searching, reset)
                    self._set(shown=len(rows))
                    if self._pending_reveal:
                        row = self.model.indexOf(self._pending_reveal)
                        self._pending_reveal = None
                        if row >= 0:
                            self.revealed.emit(row)
            elif kind == 'error':
                self._set(busy=False, progress=-1.0)
                self._error(payload)
            else:
                callback, result, cancelled = payload
                self._set(busy=False, progress=-1.0)
                if cancelled:
                    self._status(self._cancelled_key)
                else:
                    callback(result)

    # ── Mappatura / Mapping ─────────────────────────────────────────────
    @Slot(str)
    def setPath(self, value):
        if self._state['busy']:
            return
        url = QUrl(value)
        path = url.toLocalFile() if url.isLocalFile() else value.strip().strip('"')
        if path != self._state['path']:
            self._filter_revision += 1
            self._tree = None
            self._extensions = []
            self.extensionsChanged.emit()
            self._expanded.clear()
            self._scanned_root = None
            self.model.replace(array('i'), None, frozenset(), False, True)
            self._set(scanned=False, total=0, files=0, folders=0, links=0, errors=0, excluded=0, truncated=0,
                      shown=0, query='', extension='', rootName='')
        self._set(path=path)

    @Slot(str)
    def openFolder(self, value):
        """
        Imposta il percorso e avvia subito la mappatura (sfoglia, trascina, recenti).
        Sets the path and starts mapping right away (browse, drop, recent).
        Un file trascinato apre la sua cartella / A dropped file opens its folder.
        """
        url = QUrl(value)
        path = url.toLocalFile() if url.isLocalFile() else value.strip().strip('"')
        if path and os.path.isfile(extended(normalize(os.path.expanduser(path)))):
            path = os.path.dirname(path)
        # Un percorso errato non cancella la mappa attuale / A wrong path keeps the current map
        if self._state['busy']:
            return
        if not path:
            self._status('no_path', error=True)
            return
        if not os.path.isdir(extended(normalize(os.path.expanduser(path)))):
            self._status('invalid_path', error=True)
            return
        self.setPath(path)
        self.scan()

    @Slot()
    def scan(self):
        if self._state['busy']:
            return
        if not self._state['path']:
            self._status('no_path', error=True)
            return
        root = resolve(os.path.expanduser(self._state['path']))
        if not os.path.isdir(extended(root)):
            self._status('invalid_path', error=True)
            return
        self._set(path=root, found=0)
        self._status('scanning')
        excludes = Excludes.from_text(self._state['excludePatterns'], self._state['excludeTechnical'])
        levels = self._state['maxLevels'] or None
        def job(cancel):
            tree = scan_tree(root, excludes=excludes, levels=levels, cancel=cancel,
                             progress=lambda n: self._queue.put(('found', n)))
            # Indice delle cartelle pronto nel worker, non nel thread dell'interfaccia
            # Folder index built in the worker, not on the UI thread
            tree.dir_index()
            return tree
        def done(tree):
            same_root = root == self._scanned_root
            # Un nuovo scan della stessa cartella mantiene le cartelle aperte
            # Re-mapping the same folder keeps open folders open
            folders = tree.dir_index()
            self._expanded = {p for p in self._expanded if p in folders} if same_root else set()
            self._tree = tree
            self._scanned_root = root
            self._extensions = [dict(label=ext, count=n, fraction=n / max(tree.files, 1))
                                for ext, n in tree.extensions.most_common()]
            self.extensionsChanged.emit()
            self._remember(root)
            self._set(scanned=True, total=len(tree), folders=tree.folders, files=tree.files, links=tree.links,
                      errors=len(tree.errors), excluded=tree.excluded, truncated=tree.truncated,
                      rootName=os.path.basename(root) or root)
            if self._note:
                note, self._note = self._note, None
                note()
            else:
                parts = []
                if tree.excluded:
                    parts.append(self._part('status_excluded', count=tree.excluded))
                if tree.truncated:
                    parts.append(self._part('status_truncated', count=tree.truncated))
                if tree.errors:
                    parts.append(self._part('status_errors', errors=len(tree.errors)))
                self._status('scan_complete', parts=parts, count=len(tree))
            self._filter(reset=not same_root)
        self._work(job, done)

    def _remember(self, root):
        self._recent = [root] + [p for p in self._recent if os.path.normcase(p) != os.path.normcase(root)]
        del self._recent[MAX_RECENT:]
        self.recentChanged.emit()
        self._save_config()

    @Slot()
    def clearRecent(self):
        self._recent = []
        self.recentChanged.emit()
        self._save_config()

    @Slot()
    def cancel(self):
        if self._state['cancellable']:
            self._cancel.set()

    # ── Filtri, albero, ricerca / Filters, tree, search ─────────────────
    @Slot(str)
    def setQuery(self, query):
        if query == self._state['query']:
            return
        self._set(query=query)
        self._filter_revision += 1
        self._filter_timer.start(160)

    @Slot(str)
    def setExtension(self, extension):
        self._set(extension='' if extension == self._state['extension'] else extension)
        self._filter()

    @Slot()
    def clearFilters(self):
        self._filter_timer.stop()
        self._set(query='', extension='')
        self._filter()

    def _filter(self, reset=False):
        self._filter_revision += 1
        revision, tree = self._filter_revision, self._tree
        query, ext = self._state['query'].casefold().strip(), self._state['extension']
        expanded = frozenset(self._expanded)
        searching = bool(query or ext)
        def run():
            rows = array('i')
            if tree is not None and searching:
                kinds = tree.kinds
                for i, name in enumerate(tree.names):
                    if query and query not in name.casefold():
                        continue
                    if ext and (kinds[i] != FILE or (tree.extension(i) or NO_EXTENSION) != ext):
                        continue
                    rows.append(i)
            elif tree is not None:
                # Visita solo ciò che è visibile: una cartella chiusa salta il suo sottoalbero
                # Visits only what is visible: a closed folder skips its subtree
                folders = tree.dir_index()
                open_dirs = {folders[p] for p in expanded if p in folders}
                kinds, ends, i, n = tree.kinds, tree.ends, 0, len(tree)
                while i < n:
                    rows.append(i)
                    i = i + 1 if kinds[i] == DIR and i in open_dirs else ends[i]
            if not self._closed:
                self._queue.put(('filter', (revision, rows, tree, expanded, searching, reset)))
        threading.Thread(target=run, daemon=True).start()

    @Slot(str)
    def toggle(self, path):
        key = os.path.normcase(path)
        if key in self._expanded:
            self._expanded.remove(key)
        else:
            self._expanded.add(key)
        self._filter()

    @Slot(str, bool)
    def setExpanded(self, path, expanded):
        if (os.path.normcase(path) in self._expanded) != expanded:
            self.toggle(path)

    @Slot(bool)
    def expandAll(self, expanded):
        self._expanded = set(self._tree.dir_index()) if expanded and self._tree else set()
        self._filter()

    @Slot(str)
    def reveal(self, path):
        """
        Mostra un risultato di ricerca nell'albero: apre le cartelle antenate e lo seleziona.
        Shows a search result in the tree: opens its ancestor folders and selects it.
        """
        root = self._scanned_root
        if not root:
            return
        current = root
        for part in Path(os.path.relpath(path, root)).parts[:-1]:
            current = os.path.join(current, part)
            self._expanded.add(os.path.normcase(current))
        self._pending_reveal = path
        self.clearFilters()

    # ── Azioni sui file / File actions ──────────────────────────────────
    @Slot(str)
    def openPath(self, path):
        try:
            target = self._checked(path)[0]
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(target))):
                raise OSError(str(target))
        except (OSError, UserError) as exc:
            self._error(exc)

    @Slot(str)
    def showInFolder(self, path):
        """Apre Esplora risorse con l'elemento selezionato / Opens Explorer with the item selected."""
        try:
            target = self._checked(path)[0]
            if sys.platform == 'win32':
                subprocess.Popen(['explorer', f'/select,{target}'])
            elif not QDesktopServices.openUrl(QUrl.fromLocalFile(str(target.parent))):
                raise OSError(str(target.parent))
        except (OSError, UserError) as exc:
            self._error(exc)

    @Slot(str)
    def copyPath(self, path):
        QGuiApplication.clipboard().setText(path)
        self._status('path_copied')

    @Slot()
    def copyMap(self):
        if self._tree:
            QGuiApplication.clipboard().setText(self.map_text())
            self._status('map_copied')

    @Slot(str)
    def exportMap(self, url):
        """
        Salva la mappa dell'ultima scansione (la stessa dell'anteprima), in modo atomico.
        Saves the latest scan's map (the same as the preview), atomically.
        """
        self.saveExport(url, 'txt', '', False, True)

    @Slot(str, str)
    def clipboard(self, path, mode):
        try:
            target, resolved = self._checked(path)
            self._clipboard = (str(target), mode, resolved)
            self._set(clipboard=str(target), clipboardMode=mode)
            self._status('clipboard_ready', name=os.path.basename(path))
        except (UserError, OSError) as exc:
            self._error(exc)

    @Slot(str, result=bool)
    def isValidName(self, name):
        try:
            self._name(name)
            return True
        except UserError:
            return False

    def _checked(self, path):
        """
        Percorso dentro la radice mappata, confrontato dopo aver risolto link, '..' e nomi 8.3.
        Restituisce (percorso, percorso risolto) per poterlo ricontrollare prima di agire.
        Path inside the mapped root, compared after resolving links, '..' and 8.3 names.
        Returns (path, resolved path) so it can be checked again right before acting.
        """
        target = normalize(path)
        resolved = resolve(target)
        if not inside(resolved, resolve(self._state['path'])):
            raise UserError('error_outside_root')
        return Path(target), resolved

    def _recheck(self, target, resolved):
        """
        Nel worker, subito prima di agire: il percorso non deve essere cambiato dopo il clic
        (es. cartella sostituita da una junction verso l'esterno).
        In the worker, right before acting: the path must not have changed since the click
        (e.g. a folder swapped for a junction pointing outside).
        """
        now = resolve(target)
        if os.path.normcase(now) != os.path.normcase(resolved) or not inside(now, resolve(self._state['path'])):
            raise UserError('error_path_changed')

    @staticmethod
    def _name(name):
        reserved = {'CON', 'PRN', 'AUX', 'NUL'} | {f'{p}{i}' for p in ('COM', 'LPT') for i in range(1, 10)}
        if (not name or name in ('.', '..') or name[-1] in ' .' or
                any(c in '\\/:*?"<>|' or ord(c) < 32 for c in name) or name.split('.')[0].upper() in reserved):
            raise UserError('error_invalid_name')
        return name

    @staticmethod
    def _trash(path):
        """Sposta nel Cestino; mai eliminazione definitiva / Moves to the Recycle Bin; never deletes for good."""
        if not QFile.moveToTrash(str(path)):
            raise UserError('error_trash')

    def _copy_name(self, dest):
        """'nome - copia.ext', poi 'nome - copia (2).ext' … / 'name - copy.ext', then '(2)' …"""
        is_dir = os.path.isdir(extended(str(dest)))
        stem, suffix = (dest.name, '') if is_dir else (dest.stem, dest.suffix)
        base = stem + self._translations['copy_suffix']
        candidate, n = dest.with_name(base + suffix), 2
        while os.path.lexists(extended(str(candidate))):
            candidate, n = dest.with_name(f'{base} ({n}){suffix}'), n + 1
        return candidate

    @Slot(str, str, str)
    def fileAction(self, action, path, name=''):
        if self._state['busy']:
            return
        try:
            target, resolved = self._checked(path)
            root = resolve(self._state['path'])
            if os.path.normcase(resolved) == os.path.normcase(root) and action in ('delete', 'rename', 'clone'):
                raise UserError('error_root_locked')
            if action in ('rename', 'new_file', 'new_folder'):
                name = self._name(name)
            clipboard = self._clipboard
            if action not in ('delete', 'rename', 'new_file', 'new_folder', 'paste', 'clone') or (
                    action == 'paste' and not clipboard):
                return
            def exists(p):
                return os.path.lexists(extended(str(p)))
            def is_dir(p):
                return os.path.isdir(extended(str(p)))
            def job(cancel):
                self._recheck(target, resolved)
                if action == 'delete':
                    self._trash(target)
                elif action == 'rename':
                    dest = target.with_name(name)
                    # Su Windows cambiare solo le maiuscole è lecito / Case-only renames are legal on Windows
                    if exists(dest) and not os.path.samefile(extended(str(dest)), extended(str(target))):
                        raise UserError('error_name_exists')
                    os.rename(extended(str(target)), extended(str(dest)))
                elif action in ('new_file', 'new_folder'):
                    dest = (target if is_dir(target) else target.parent) / name
                    if exists(dest):
                        raise UserError('error_name_exists')
                    if action == 'new_folder':
                        os.mkdir(extended(str(dest)))
                    else:
                        with open(extended(str(dest)), 'x'):
                            pass
                else:
                    if action == 'paste':
                        source = Path(clipboard[0])
                        self._recheck(source, clipboard[2])
                        dest = (target if is_dir(target) else target.parent) / source.name
                    else:
                        source, dest = target, target
                    if not exists(source):
                        raise UserError('error_source_missing')
                    move = action == 'paste' and clipboard[1] == 'cut'
                    if move and exists(dest) and os.path.samefile(extended(str(dest)), extended(str(source))):
                        return
                    source_real = resolve(source)
                    # Mai copiare o spostare una cartella dentro sé stessa (anche tramite junction)
                    # Never copy or move a folder into itself (junctions included)
                    if is_dir(source) and inside(resolve(dest.parent), source_real) and (move or dest != source):
                        raise UserError('error_copy_into_self')
                    if exists(dest):
                        if move:
                            raise UserError('error_name_exists')
                        dest = self._copy_name(dest)
                    if is_dir(source) and not move and inside(resolve(dest.parent), source_real):
                        raise UserError('error_copy_into_self')
                    if move:
                        report = fsops.move(source, dest)
                    elif is_dir(source):
                        report = fsops.copy_tree(source, dest)
                    else:
                        shutil.copy2(extended(str(source)), extended(str(dest)), follow_symlinks=False)
                        report = fsops.CopyReport()
                    if report.skipped:
                        skipped = len(report.skipped)
                        self._note = lambda: self._status('links_skipped', count=skipped)
            def done(_):
                if action == 'paste' and clipboard[1] == 'cut':
                    self._clipboard = None
                    self._set(clipboard='', clipboardMode='')
                self.scan()
            self._status('working')
            self._work(job, done, cancellable=False)
        except (UserError, OSError) as exc:
            self._error(exc)

    # ── Preferenze / Preferences ────────────────────────────────────────
    def _apply(self, theme, language, reduced):
        if theme not in THEMES or language not in LANGUAGES:
            return False
        language_changed = language != self._state['language']
        self._set(theme=theme, language=language, reducedMotion=bool(reduced))
        if language_changed:
            self._translations = self._load_translations()
            self.translationsChanged.emit()
            if self._status_source:
                key, values, error, parts = self._status_source
                self._status(key, error, parts, **values)
        return True

    @Slot(str, str, bool)
    def previewPreferences(self, theme, language, reduced):
        """Anteprima dal vivo senza salvare / Live preview without saving."""
        self._apply(theme, language, reduced)

    @Slot(str, str, bool)
    def preferences(self, theme, language, reduced):
        if self._apply(theme, language, reduced):
            self._save_config()

    @Slot()
    def shutdown(self):
        self._closed = True
        self._cancel.set()
        self._timer.stop()
        self._filter_timer.stop()
