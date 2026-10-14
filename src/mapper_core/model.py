"""
Modello dati: l'albero è salvato per colonne in ordine di visita (pre-order), così ogni elemento
costa pochi byte; percorsi, estensioni e righe della mappa si calcolano solo quando servono.
Data model: the tree is stored as columns in visit order (pre-order), so each item costs a few
bytes; paths, extensions and map lines are computed only when needed.
"""
import os
from array import array
from collections import Counter
from dataclasses import dataclass

FILE, DIR, LINK = 0, 1, 2
KIND_NAMES = ('file', 'dir', 'link')
NO_EXTENSION = '—'
BRANCH, LAST, PIPE, SPACE = '├── ', '└── ', '│   ', '    '


def root_label(root):
    """Nome della radice nella mappa ('D:' per un'unità) / Root name in the map ('D:' for a drive)."""
    root = os.path.normpath(root)
    return (os.path.basename(root) or root.rstrip('\\/')) + '/'


@dataclass(frozen=True, slots=True)
class ScanError:
    """
    Elemento non letto: la scansione continua. reason: access_denied, not_found, path_too_long,
    depth_limit, error.
    Item that could not be read: the scan goes on.
    """
    path: str
    reason: str
    detail: str = ''


class Tree:
    """
    Risultato di una scansione. L'indice i identifica un elemento; parents[i] è l'indice della
    cartella che lo contiene (-1 = radice), ends[i] l'indice dopo l'ultimo discendente.
    Result of a scan. Index i identifies an item; parents[i] is the containing folder (-1 = root),
    ends[i] the index after its last descendant.
    """

    def __init__(self, root, metadata=True):
        self.root = root
        self.metadata = metadata
        self.names = []
        self.parents = array('i')
        self.ends = array('i')
        self.levels = array('H')
        self.kinds = bytearray()
        self.last = bytearray()
        # Metadati (vuoti se metadata=False): byte, secondi epoch, attributi Windows
        # Metadata (empty when metadata=False): bytes, epoch seconds, Windows attributes
        self.sizes = array('q')
        self.mtimes = array('d')
        self.attributes = array('L')
        self.errors = []
        self.extensions = Counter()
        self.folders = self.files = self.links = 0
        self.cancelled = False
        self._prefix = root if root.endswith(('\\', '/')) else root + os.sep
        self._dir_paths = {}
        self._dir_index = None

    def __len__(self):
        return len(self.names)

    # ── Accesso per indice / Index access ───────────────────────────────
    def kind(self, i):
        return self.kinds[i]

    def is_dir(self, i):
        return self.kinds[i] == DIR

    def dir_path(self, i):
        """Percorso completo di una cartella (con cache) / Full path of a folder (cached)."""
        cache = self._dir_paths
        path = cache.get(i)
        if path is not None:
            return path
        # Risale fino a un antenato già noto (iterativo: nessun limite di ricorsione)
        # Climbs to an already known ancestor (iterative: no recursion limit)
        chain, j = [], i
        while j >= 0 and j not in cache:
            chain.append(j)
            j = self.parents[j]
        path = self.root if j < 0 else cache[j]
        for j in reversed(chain):
            path = os.path.join(path, self.names[j])
            cache[j] = path
        return path

    def parent_path(self, i):
        parent = self.parents[i]
        return self.root if parent < 0 else self.dir_path(parent)

    def path(self, i):
        if self.kinds[i] == DIR:
            return self.dir_path(i)
        return os.path.join(self.parent_path(i), self.names[i])

    def relative(self, i):
        return self.path(i)[len(self._prefix):]

    def extension(self, i):
        """Estensione minuscola dei file ('' per cartelle e collegamenti) / Lower-case file extension."""
        return os.path.splitext(self.names[i])[1].lower() if self.kinds[i] == FILE else ''

    def size(self, i):
        return self.sizes[i] if self.metadata else -1

    def mtime(self, i):
        return self.mtimes[i] if self.metadata else 0.0

    # ── Navigazione / Navigation ────────────────────────────────────────
    def children(self, i=-1):
        """Indici dei figli diretti (i=-1: radice) / Indices of direct children (i=-1: root)."""
        j, end = (0, len(self.names)) if i < 0 else (i + 1, self.ends[i])
        while j < end:
            yield j
            j = self.ends[j]

    def dir_index(self):
        """
        {percorso normcase: indice} di tutte le cartelle, costruito una volta.
        {normcase path: index} of every folder, built once.
        """
        index = self._dir_index
        if index is None:
            normcase, dir_path = os.path.normcase, self.dir_path
            index = {normcase(dir_path(i)): i for i, kind in enumerate(self.kinds) if kind == DIR}
            self._dir_index = index
        return index

    def index_of(self, path):
        """Indice di un percorso completo, -1 se assente / Index of a full path, -1 if missing."""
        target = os.path.normcase(os.path.normpath(path))
        found = self.dir_index().get(target)
        if found is not None:
            return found
        parent = os.path.dirname(target)
        if parent == os.path.normcase(self.root):
            parent_index = -1
        else:
            parent_index = self.dir_index().get(parent)
            if parent_index is None:
                return -1
        name = os.path.basename(target)
        return next((j for j in self.children(parent_index) if os.path.normcase(self.names[j]) == name), -1)

    # ── Mappa testuale (formato 1.5) / Text map (1.5 format) ────────────
    def lines(self):
        """Righe della mappa Unicode, identiche alla 1.5 / Unicode map lines, identical to 1.5."""
        yield root_label(self.root)
        prefixes = ['']
        names, levels, kinds, last = self.names, self.levels, self.kinds, self.last
        for i in range(len(names)):
            level = levels[i]
            prefix = prefixes[level]
            is_last = last[i]
            if kinds[i] == DIR:
                del prefixes[level + 1:]
                prefixes.append(prefix + (SPACE if is_last else PIPE))
                yield prefix + (LAST if is_last else BRANCH) + names[i] + '/'
            else:
                yield prefix + (LAST if is_last else BRANCH) + names[i]

    def line_count(self):
        return len(self.names) + 1
