r"""
Percorsi Windows: forma estesa \\?\ per superare il limite di 260 caratteri.
Windows paths: extended \\?\ form to go past the 260-character limit.
"""
import errno
import os

EXTENDED, EXTENDED_UNC = '\\\\?\\', '\\\\?\\UNC\\'


def normalize(path):
    """Percorso assoluto e normalizzato, senza prefisso esteso / Absolute, normalized, no extended prefix."""
    return os.path.abspath(display(os.fspath(path)))


def extended(path):
    """
    Forma estesa per le chiamate al sistema (Windows) / Extended form for system calls (Windows).
    Richiede un percorso assoluto e normalizzato / Needs an absolute, normalized path.
    """
    if os.name != 'nt' or path.startswith(EXTENDED):
        return path
    if path.startswith('\\\\'):
        return EXTENDED_UNC + path[2:]
    return EXTENDED + path


def display(path):
    """Toglie il prefisso esteso per mostrare il percorso / Removes the extended prefix for display."""
    if path.startswith(EXTENDED_UNC):
        return '\\\\' + path[len(EXTENDED_UNC):]
    if path.startswith(EXTENDED):
        return path[len(EXTENDED):]
    return path


def error_reason(exc):
    """Classifica un OSError per l'utente / Classifies an OSError for the user."""
    winerror = getattr(exc, 'winerror', None)
    if winerror in (5, 32) or exc.errno in (errno.EACCES, errno.EPERM):
        return 'access_denied'
    if winerror in (2, 3, 21) or exc.errno == errno.ENOENT:
        return 'not_found'
    if winerror in (206, 1450) or exc.errno == errno.ENAMETOOLONG:
        return 'path_too_long'
    return 'error'
