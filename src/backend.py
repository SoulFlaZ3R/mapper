"""
Qt models and async filesystem services; workers never touch Qt objects.
Modelli Qt e servizi asincroni sul filesystem; i worker non toccano oggetti Qt.
"""
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from PySide6.QtCore import (QAbstractListModel, QFile, QLocale, QModelIndex, QObject, Property,
                            QTimer, Qt, QUrl, Signal, Slot)
from PySide6.QtGui import QDesktopServices, QGuiApplication
from scanner import count_items, snapshot

VERSION = '1.5.0'
THEMES = ('light', 'dark', 'blue', 'red', 'system')
LANGUAGES = ('it', 'en', 'de', 'fr', 'es')
PREVIEW_LINES = 1200
MAX_RECENT = 6

BASE = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
CONFIG = (Path(sys.executable).parent if getattr(sys, 'frozen', False) else BASE) / 'config.json'


class UserError(Exception):
    """Errore con messaggio tradotto / Error carrying a translation key."""
    def __init__(self, key):
        super().__init__(key)
        self.key = key


class FileModel(QAbstractListModel):
    fields = ('itemName', 'fullPath', 'directory', 'level', 'expanded', 'extension', 'relativePath', 'parentPath')

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []

    def roleNames(self):
        return {Qt.UserRole + i + 1: name.encode() for i, name in enumerate(self.fields)}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index, role):
        i = role - Qt.UserRole - 1
        if index.isValid() and 0 <= index.row() < len(self.rows) and 0 <= i < len(self.fields):
            return self.rows[index.row()].get(self.fields[i])
        return None

    @Slot(str, result=int)
    def indexOf(self, path):
        for i, row in enumerate(self.rows):
            if row['fullPath'] == path:
                return i
        return -1

    def replace(self, rows, reset=False):
        """
        Aggiorna con rimozioni/inserimenti minimi così la vista mantiene scroll e selezione.
        Updates with minimal removals/insertions so the view keeps scroll and selection.
        """
        old = self.rows
        if reset or not old or not rows:
            self.beginResetModel()
            self.rows = rows
            self.endResetModel()
            return
        n, m = len(old), len(rows)
        head = 0
        while head < min(n, m) and old[head]['fullPath'] == rows[head]['fullPath']:
            head += 1
        tail = 0
        while tail < min(n, m) - head and old[n - 1 - tail]['fullPath'] == rows[m - 1 - tail]['fullPath']:
            tail += 1
        # Righe rimaste al loro posto ma con dati diversi (es. freccia espansa)
        # Rows that kept their place but changed data (e.g. expanded arrow)
        changed = [i for i in range(head) if old[i] != rows[i]]
        changed += [m - 1 - j for j in range(tail) if old[n - 1 - j] != rows[m - 1 - j]]
        if n - tail > head:
            self.beginRemoveRows(QModelIndex(), head, n - tail - 1)
            self.rows = old[:head] + old[n - tail:]
            self.endRemoveRows()
        if m - tail > head:
            self.beginInsertRows(QModelIndex(), head, m - tail - 1)
            self.rows = self.rows[:head] + rows[head:m - tail] + self.rows[head:]
            self.endInsertRows()
        self.rows = rows
        changed.sort()
        if changed:
            self.dataChanged.emit(self.index(changed[0]), self.index(changed[-1]))


class MapperBackend(QObject):
    changed = Signal()
    translationsChanged = Signal()
    extensionsChanged = Signal()
    recentChanged = Signal()
    revealed = Signal(int)

    def __init__(self, config_path=None):
        super().__init__()
        self.config_path = Path(config_path or CONFIG)
        self.model = FileModel(self)
        self._state = dict(path='', busy=False, progress=-1.0, status='', error=False, scanned=False,
                           total=0, folders=0, files=0, shown=0, query='', extension='',
                           theme='light', language='en', reducedMotion=False, clipboard='',
                           clipboardMode='', version=VERSION, cancellable=True, rootName='',
                           previewLimit=PREVIEW_LINES)
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
        self._translations = self._load_translations()
        self._records, self._lines, self._extensions = [], [], []
        self._expanded = set()
        self._scanned_root = None
        self._status_source = None
        self._pending_reveal = None
        self._clipboard = None
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
        return '\n'.join(self._lines[:PREVIEW_LINES])

    @Slot(result=int)
    def lineCount(self):
        return len(self._lines)

    # ── Stato, traduzioni, errori / State, translations, errors ─────────
    def _load_translations(self):
        data = json.loads((BASE / 'Languages' / 'en.json').read_text(encoding='utf-8'))
        data.update(json.loads((BASE / 'Languages' / (self._state['language'] + '.json')).read_text(encoding='utf-8')))
        return data

    def _set(self, **values):
        self._state.update(values)
        self.changed.emit()

    def _status(self, key, error=False, **values):
        # Conserva la chiave per ritradurre al cambio lingua / Keep the key to re-translate on language change
        self._status_source = (key, values, error)
        self._set(status=self._translations[key].format(**values), error=error)

    def _error(self, exc):
        if isinstance(exc, UserError):
            self._status(exc.key, error=True)
        else:
            self._status('error_operation', error=True, details=str(exc))

    def _save_config(self):
        prefs = dict(theme=self._state['theme'], language=self._state['language'],
                     reducedMotion=self._state['reducedMotion'], recent=self._recent)
        try:
            self.config_path.write_text(json.dumps(prefs, indent=2, ensure_ascii=False), encoding='utf-8')
        except OSError as exc:
            self._error(exc)

    # ── Lavori in background / Background jobs ──────────────────────────
    def _work(self, job, done, cancellable=True):
        if self._state['busy']:
            return False
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
            if kind == 'progress':
                self._set(progress=payload)
            elif kind == 'filter':
                revision, rows, reset = payload
                if revision == self._filter_revision:
                    self.model.replace(rows, reset)
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
                    self._status('scan_cancelled')
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
            self._records, self._lines = [], []
            self._extensions = []
            self.extensionsChanged.emit()
            self._expanded.clear()
            self._scanned_root = None
            self.model.replace([], True)
            self._set(scanned=False, total=0, files=0, folders=0, shown=0, query='', extension='', rootName='')
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
        if os.path.isfile(path):
            path = os.path.dirname(path)
        # Un percorso errato non cancella la mappa attuale / A wrong path keeps the current map
        if self._state['busy']:
            return
        if not path:
            self._status('no_path', error=True)
            return
        if not os.path.isdir(os.path.expanduser(path)):
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
        root = os.path.realpath(os.path.expanduser(self._state['path']))
        if not os.path.isdir(root):
            self._status('invalid_path', error=True)
            return
        self._set(path=root)
        self._status('scanning')
        def job(cancel):
            total = max(count_items(root, cancel), 1)
            last = [-1]
            def progress(n):
                pct = min(100, int(n * 100 / total))
                if pct != last[0]:
                    last[0] = pct
                    self._queue.put(('progress', pct / 100))
            return snapshot(root, cancel, progress)
        def done(result):
            self._records, self._lines, counts, folders, files = result
            same_root = root == self._scanned_root
            # Un nuovo scan della stessa cartella mantiene le cartelle aperte
            # Re-mapping the same folder keeps open folders open
            folders_now = {r['fullPath'] for r in self._records if r['directory']}
            self._expanded = self._expanded & folders_now if same_root else set()
            self._scanned_root = root
            self._extensions = [dict(label=ext, count=n, fraction=n / max(files, 1)) for ext, n in counts.most_common()]
            self.extensionsChanged.emit()
            self._remember(root)
            self._set(scanned=True, total=len(self._records), folders=folders, files=files,
                      rootName=os.path.basename(root) or root)
            self._status('scan_complete', count=len(self._records))
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
        revision, records = self._filter_revision, self._records
        query, ext = self._state['query'].casefold().strip(), self._state['extension']
        expanded, root = set(self._expanded), self._scanned_root
        def run():
            rows, visible_dirs = [], {root}
            searching = bool(query or ext)
            for record in records:
                if searching:
                    if query not in record['itemName'].casefold():
                        continue
                    if ext and (record['directory'] or (record['extension'] or '—') != ext):
                        continue
                elif record['parentPath'] not in visible_dirs:
                    continue
                row = dict(record, expanded=record['fullPath'] in expanded)
                if searching:
                    row['level'] = 0
                elif row['expanded']:
                    visible_dirs.add(record['fullPath'])
                rows.append(row)
            if not self._closed:
                self._queue.put(('filter', (revision, rows, reset)))
        threading.Thread(target=run, daemon=True).start()

    @Slot(str)
    def toggle(self, path):
        if path in self._expanded:
            self._expanded.remove(path)
        else:
            self._expanded.add(path)
        self._filter()

    @Slot(str, bool)
    def setExpanded(self, path, expanded):
        if (path in self._expanded) != expanded:
            self.toggle(path)

    @Slot(bool)
    def expandAll(self, expanded):
        self._expanded = {r['fullPath'] for r in self._records if r['directory']} if expanded else set()
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
            self._expanded.add(current)
        self._pending_reveal = path
        self.clearFilters()

    # ── Azioni sui file / File actions ──────────────────────────────────
    @Slot(str)
    def openPath(self, path):
        try:
            target = self._checked(path)
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(target))):
                raise OSError(str(target))
        except (OSError, UserError) as exc:
            self._error(exc)

    @Slot(str)
    def showInFolder(self, path):
        """Apre Esplora risorse con l'elemento selezionato / Opens Explorer with the item selected."""
        try:
            target = self._checked(path)
            if sys.platform == 'win32':
                subprocess.Popen(f'explorer /select,"{target}"')
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
        if self._lines:
            QGuiApplication.clipboard().setText('\n'.join(self._lines))
            self._status('map_copied')

    @Slot(str)
    def exportMap(self, url):
        """
        Salva la mappa dell'ultima scansione (la stessa dell'anteprima), in modo atomico.
        Saves the latest scan's map (the same as the preview), atomically.
        """
        if not self._state['scanned'] or self._state['busy']:
            return
        destination = QUrl(url).toLocalFile() if QUrl(url).isLocalFile() else url
        text = '\n'.join(self._lines) + '\n'
        def job(cancel):
            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=Path(destination).parent,
                                                 prefix='.mapper-', suffix='.tmp', delete=False) as handle:
                    temp_path = handle.name
                    handle.write(text)
                if not cancel.is_set():
                    os.replace(temp_path, destination)
            finally:
                if temp_path and os.path.exists(temp_path):
                    os.unlink(temp_path)
            return destination
        self._work(job, lambda path: self._status('saved_to', path=path))

    @Slot(str, str)
    def clipboard(self, path, mode):
        try:
            self._clipboard = (str(self._checked(path)), mode)
            self._set(clipboard=self._clipboard[0], clipboardMode=mode)
            self._status('clipboard_ready', name=os.path.basename(path))
        except UserError as exc:
            self._error(exc)

    @Slot(str, result=bool)
    def isValidName(self, name):
        try:
            self._name(name)
            return True
        except UserError:
            return False

    def _checked(self, path):
        # Confronto su percorsi risolti: gestisce nomi brevi 8.3 (RUNNER~1), '..' e link
        # Compare resolved paths: handles 8.3 short names (RUNNER~1), '..' and links
        root, target = Path(self._state['path']).resolve(), Path(path).absolute()
        if not target.resolve().is_relative_to(root):
            raise UserError('error_outside_root')
        return target

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
        stem, suffix = (dest.name, '') if dest.is_dir() else (dest.stem, dest.suffix)
        base = stem + self._translations['copy_suffix']
        candidate, n = dest.with_name(base + suffix), 2
        while candidate.exists():
            candidate, n = dest.with_name(f'{base} ({n}){suffix}'), n + 1
        return candidate

    @Slot(str, str, str)
    def fileAction(self, action, path, name=''):
        if self._state['busy']:
            return
        try:
            target = self._checked(path)
            if target.resolve() == Path(self._state['path']).resolve() and action in ('delete', 'rename', 'clone'):
                raise UserError('error_root_locked')
            if action in ('rename', 'new_file', 'new_folder'):
                name = self._name(name)
            clipboard = self._clipboard
            if action not in ('delete', 'rename', 'new_file', 'new_folder', 'paste', 'clone') or (
                    action == 'paste' and not clipboard):
                return
            def job(cancel):
                if action == 'delete':
                    self._trash(target)
                elif action == 'rename':
                    dest = target.with_name(name)
                    # Su Windows cambiare solo le maiuscole è lecito / Case-only renames are legal on Windows
                    if dest.exists() and not dest.samefile(target):
                        raise UserError('error_name_exists')
                    target.rename(dest)
                elif action in ('new_file', 'new_folder'):
                    dest = (target if target.is_dir() else target.parent) / name
                    if dest.exists():
                        raise UserError('error_name_exists')
                    if action == 'new_folder':
                        dest.mkdir()
                    else:
                        with dest.open('x'):
                            pass
                else:
                    if action == 'paste':
                        source = self._checked(clipboard[0])
                        dest = (target if target.is_dir() else target.parent) / source.name
                    else:
                        source, dest = target, target
                    if not source.exists():
                        raise UserError('error_source_missing')
                    move = action == 'paste' and clipboard[1] == 'cut'
                    if move and dest.exists() and dest.samefile(source):
                        return
                    if source.is_dir() and dest.resolve().is_relative_to(source.resolve()) and (move or dest != source):
                        raise UserError('error_copy_into_self')
                    if dest.exists():
                        if move:
                            raise UserError('error_name_exists')
                        dest = self._copy_name(dest)
                    if move:
                        shutil.move(str(source), str(dest))
                    elif source.is_dir():
                        shutil.copytree(source, dest, symlinks=True)
                    else:
                        shutil.copy2(source, dest, follow_symlinks=False)
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
                key, values, error = self._status_source
                self._status(key, error, **values)
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
