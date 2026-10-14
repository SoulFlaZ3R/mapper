"""
Core di Mapper: logica pura sul filesystem, senza Qt (usata da GUI e, in futuro, CLI).
Mapper core: pure filesystem logic, no Qt (used by the GUI and, later, the CLI).
"""
from .model import DIR, FILE, LINK, ScanError, Tree, root_label
from .walker import MAX_DEPTH, scan

__all__ = ['DIR', 'FILE', 'LINK', 'MAX_DEPTH', 'ScanError', 'Tree', 'root_label', 'scan']
