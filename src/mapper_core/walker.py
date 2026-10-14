r"""
Visita del filesystem: una sola passata, annullabile, senza seguire symlink e junction.
Filesystem walk: a single pass, cancellable, never following symlinks or junctions.

- Percorsi oltre 260 caratteri letti con il prefisso \\?\ / Paths over 260 characters read via \\?\
- Errori raccolti in Tree.errors, la visita continua / Errors collected in Tree.errors, the walk goes on
- Ordine: cartelle prima, poi file, senza distinzione di maiuscole (come la 1.5)
  Order: folders first, then files, case-insensitive (as in 1.5)
"""
import os

from .model import DIR, FILE, LINK, NO_EXTENSION, ScanError, Tree
from .paths import display, error_reason, extended, normalize

# File esclusi sempre (come la 1.5) / Always skipped (as in 1.5)
SKIP_FILES = frozenset({'desktop.ini'})
# Limite di profondità contro percorsi patologici / Depth guard against pathological paths
MAX_DEPTH = 500
_END = None


def _attributes(stat_result):
    return getattr(stat_result, 'st_file_attributes', 0)


def _read(io_path, metadata):
    """Elementi di una cartella come tuple / A folder's entries as tuples."""
    entries = []
    with os.scandir(io_path) as it:
        for entry in it:
            name = entry.name
            if name.lower() in SKIP_FILES:
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    kind = LINK if entry.is_junction() else DIR
                else:
                    kind = LINK if entry.is_symlink() else FILE
            except OSError:
                kind = FILE
            child = entry.path if kind == DIR else None
            if metadata:
                try:
                    st = entry.stat(follow_symlinks=False)
                    entries.append((name, kind, st.st_size if kind == FILE else -1, st.st_mtime, _attributes(st), child))
                except OSError:
                    entries.append((name, kind, -1, 0.0, 0, child))
            else:
                entries.append((name, kind, -1, 0.0, 0, child))
    entries.sort(key=lambda e: (e[1] != DIR, e[0].lower()))
    return entries


def scan(root, *, metadata=True, max_depth=MAX_DEPTH, cancel=None, progress=None, progress_every=4096):
    """
    Scansiona root e restituisce un Tree. progress(n) riceve gli elementi trovati finora.
    cancel: threading.Event; se impostato, Tree.cancelled è True e il risultato è parziale.
    Scans root and returns a Tree. progress(n) receives the items found so far.
    cancel: threading.Event; when set, Tree.cancelled is True and the result is partial.
    """
    tree = Tree(normalize(root), metadata)
    names, parents, ends, levels = tree.names, tree.parents, tree.ends, tree.levels
    kinds, last, sizes, mtimes, attrs = tree.kinds, tree.last, tree.sizes, tree.mtimes, tree.attributes
    counts, errors = tree.extensions, tree.errors
    splitext = os.path.splitext
    cancelled = cancel.is_set if cancel is not None else (lambda: False)
    next_check = progress_every
    # Lo stack contiene: (cartella da leggere, indice, profondità), (_END, indice) o un elemento da emettere
    # The stack holds: (folder to read, index, depth), (_END, index) or an item to emit
    stack = [(extended(tree.root), -1, 0)]
    while stack:
        item = stack.pop()
        size = len(item)
        if size == 2:
            ends[item[1]] = len(names)
            continue
        if size == 3:
            if cancelled():
                tree.cancelled = True
                break
            io_path, index, depth = item
            try:
                entries = _read(io_path, metadata)
            except OSError as exc:
                path = tree.root if index < 0 else tree.dir_path(index)
                errors.append(ScanError(display(path), error_reason(exc), exc.strerror or ''))
                continue
            count = len(entries)
            for k in range(count - 1, -1, -1):
                stack.append(entries[k] + (k == count - 1, index, depth))
            continue
        name, kind, item_size, mtime, attr, child, is_last, parent, depth = item
        i = len(names)
        names.append(name)
        parents.append(parent)
        ends.append(i + 1)
        levels.append(depth)
        kinds.append(kind)
        last.append(is_last)
        if metadata:
            sizes.append(item_size)
            mtimes.append(mtime)
            attrs.append(attr)
        if kind == DIR:
            tree.folders += 1
            if depth < max_depth:
                stack.append((_END, i))
                stack.append((child, i, depth + 1))
            else:
                errors.append(ScanError(tree.dir_path(i), 'depth_limit'))
        elif kind == FILE:
            tree.files += 1
            counts[splitext(name)[1].lower() or NO_EXTENSION] += 1
        else:
            tree.links += 1
        if i >= next_check:
            next_check += progress_every
            if progress:
                progress(i + 1)
            if cancelled():
                tree.cancelled = True
                break
    return tree
