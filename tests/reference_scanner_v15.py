"""
Scanner module – Modulo di scansione
=====================================
Pure filesystem logic, no UI. One traversal produces both the explorer index
and the Unicode tree map, so what the user sees is exactly what gets exported.
Logica pura sul filesystem, nessuna UI. Un'unica visita produce sia l'indice
dell'esploratore sia la mappa ad albero, così ciò che si vede è ciò che si esporta.
"""

import os
from collections import Counter

# File da escludere automaticamente dalla scansione
# Files to automatically exclude from scanning
SKIP_FILES = {"desktop.ini"}

# Limite di profondità contro percorsi patologici / Depth guard against pathological paths
MAX_DEPTH = 500

BRANCH, LAST, PIPE, SPACE = "├── ", "└── ", "│   ", "    "


def _is_dir(entry):
    """
    Cartella reale: niente symlink né junction NTFS (evita cicli).
    Real directory: no symlinks or NTFS junctions (prevents cycles).
    """
    try:
        if not entry.is_dir(follow_symlinks=False):
            return False
        is_junction = getattr(entry, "is_junction", None)
        return not (is_junction and is_junction())
    except OSError:
        return False


def _sorted_entries(dir_path):
    """
    Elementi di una cartella: cartelle prima, poi file, case-insensitive.
    Directory entries: folders first, then files, case-insensitive.
    Returns a list of (name, full_path, is_dir).
    """
    try:
        with os.scandir(dir_path) as it:
            entries = [(e.name, e.path, _is_dir(e)) for e in it if e.name.lower() not in SKIP_FILES]
    except OSError:
        return []
    entries.sort(key=lambda e: (not e[2], e[0].lower()))
    return entries


def root_label(root):
    """Nome della radice nella mappa ('D:' per un'unità) / Root name in the map ('D:' for a drive)."""
    root = os.path.normpath(root)
    return (os.path.basename(root) or root.rstrip("\\/")) + "/"


def count_items(path, cancel_event=None):
    """
    Conta file e cartelle con le stesse regole di snapshot() (per la % di avanzamento).
    Counts files and folders with the same rules as snapshot() (for progress %).
    """
    total, stack = 0, [path]
    while stack:
        if cancel_event and cancel_event.is_set():
            break
        try:
            with os.scandir(stack.pop()) as it:
                for entry in it:
                    if entry.name.lower() in SKIP_FILES:
                        continue
                    total += 1
                    if _is_dir(entry):
                        stack.append(entry.path)
        except OSError:
            pass
    return total


def snapshot(root, cancel_event=None, progress_cb=None):
    """
    Visita in profondità: restituisce (records, lines, counts, folders, files).
    Depth-first walk: returns (records, lines, counts, folders, files).

    records: one dict per item, in tree order / un dict per elemento, in ordine d'albero
    lines:   Unicode tree map / mappa ad albero Unicode
    counts:  Counter of file extensions ('—' = none) / estensioni dei file
    progress_cb(n): called with the number of items processed so far
    """
    records, lines, counts = [], [root_label(root)], Counter()
    folders = files = 0
    # Lo stack contiene cartelle da leggere (str) o elementi da emettere (tuple)
    # The stack holds folders to read (str) or entries to emit (tuple)
    stack = [(root, 0, "")]
    while stack:
        if cancel_event and cancel_event.is_set():
            break
        item, depth, prefix = stack.pop()
        if isinstance(item, str):
            entries = _sorted_entries(item)
            for i in range(len(entries) - 1, -1, -1):
                stack.append((entries[i] + (i == len(entries) - 1,), depth, prefix))
            continue
        name, path, is_dir, last = item
        lines.append(prefix + (LAST if last else BRANCH) + name + ("/" if is_dir else ""))
        ext = "" if is_dir else os.path.splitext(name)[1].lower()
        records.append(dict(itemName=name, fullPath=path, directory=is_dir, level=depth,
                            extension=ext, relativePath=os.path.relpath(path, root),
                            parentPath=os.path.dirname(path)))
        if is_dir:
            folders += 1
            if depth < MAX_DEPTH:
                stack.append((path, depth + 1, prefix + (SPACE if last else PIPE)))
        else:
            files += 1
            counts[ext or "—"] += 1
        if progress_cb:
            progress_cb(len(records))
    return records, lines, counts, folders, files


def scan_folder(path, cancel_event=None, progress_cb=None):
    """
    Punto di ingresso testuale: righe della mappa ad albero.
    Text entry point: the tree map lines.
    """
    if not os.path.isdir(path):
        return []
    return snapshot(path, cancel_event, progress_cb)[1]
