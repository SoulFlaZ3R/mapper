r"""
Copia e spostamento che non seguono mai symlink e junction (shutil.copytree segue le junction).
Copy and move that never follow symlinks or junctions (shutil.copytree follows junctions).

Un collegamento viene ricreato come collegamento allo stesso target; se Windows non lo permette
(symlink senza privilegio) viene saltato e conteggiato. Tutti i percorsi passano in forma \\?\.
A link is recreated as a link to the same target; when Windows refuses (symlink without
privilege) it is skipped and counted. All paths go through the \\?\ form.
"""
import os
import shutil
from dataclasses import dataclass, field

from .paths import display, extended, normalize

try:
    from _winapi import CreateJunction
except ImportError:  # non Windows
    CreateJunction = None

ERROR_NOT_SAME_DEVICE = 17


@dataclass
class CopyReport:
    """Collegamenti ricreati e saltati / Links recreated and skipped."""
    links: int = 0
    skipped: list = field(default_factory=list)


def is_link(path):
    """Symlink o junction (senza seguirli) / Symlink or junction (not followed)."""
    path = extended(normalize(path))
    return os.path.islink(path) or os.path.isjunction(path)


def _copy_link(source, target, junction, is_dir, report):
    try:
        link_target = os.readlink(source)
        if junction:
            if CreateJunction is None:
                raise OSError('junctions are not supported')
            # Una junction con target in forma \\?\ non funziona: si usa la forma normale
            # A junction whose target uses the \\?\ form does not work: use the plain form
            CreateJunction(display(link_target), target)
        else:
            os.symlink(link_target, target, target_is_directory=is_dir)
        report.links += 1
    except OSError:
        report.skipped.append(source)


def copy_tree(source, destination):
    """
    Copia una cartella; la destinazione non deve esistere. Restituisce un CopyReport.
    Copies a folder; the destination must not exist. Returns a CopyReport.
    """
    source, destination = extended(normalize(source)), extended(normalize(destination))
    report = CopyReport()
    os.mkdir(destination)
    copied = [(source, destination)]
    stack = [(source, destination)]
    while stack:
        src_dir, dst_dir = stack.pop()
        with os.scandir(src_dir) as it:
            for entry in it:
                target = os.path.join(dst_dir, entry.name)
                junction = entry.is_junction()
                if junction or entry.is_symlink():
                    _copy_link(entry.path, target, junction, entry.is_dir(), report)
                elif entry.is_dir(follow_symlinks=False):
                    os.mkdir(target)
                    copied.append((entry.path, target))
                    stack.append((entry.path, target))
                else:
                    shutil.copy2(entry.path, target, follow_symlinks=False)
    # Date e attributi delle cartelle alla fine: copiare i figli le modifica
    # Folder dates and attributes last: copying children changes them
    for src_dir, dst_dir in reversed(copied):
        shutil.copystat(src_dir, dst_dir, follow_symlinks=False)
    return report


def remove_tree(path):
    """
    Elimina definitivamente una cartella copiata (fase finale di uno spostamento tra unità).
    Le junction vengono rimosse come collegamenti, senza toccare il loro contenuto.
    Permanently deletes a copied folder (last step of a cross-drive move).
    Junctions are removed as links, their content is never touched.
    """
    shutil.rmtree(extended(normalize(path)))


def move(source, destination):
    """
    Sposta file o cartelle: rinomina sulla stessa unità, altrimenti copia sicura e poi elimina l'origine.
    Moves files or folders: rename on the same drive, otherwise safe copy then remove the source.
    """
    src, dst = extended(normalize(source)), extended(normalize(destination))
    try:
        os.rename(src, dst)
        return CopyReport()
    except OSError as exc:
        if getattr(exc, 'winerror', None) != ERROR_NOT_SAME_DEVICE:
            raise
    if os.path.isdir(src) and not is_link(src):
        report = copy_tree(src, dst)
        # Se qualche collegamento non è stato ricreato l'originale resta dov'è (niente perdite)
        # If some link could not be recreated the original stays where it is (nothing lost)
        if not report.skipped:
            remove_tree(src)
        return report
    shutil.copy2(src, dst, follow_symlinks=False)
    os.unlink(src)
    return CopyReport()
