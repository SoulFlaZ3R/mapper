"""
Benchmark riproducibili di Mapper (Windows). Confrontare solo misure fatte sulla stessa macchina.
Reproducible Mapper benchmarks (Windows). Only compare numbers taken on the same machine.

  python benchmarks/bench.py gen <N> <cartella>        albero sintetico deterministico (~10 % cartelle)
  python benchmarks/bench.py engine <cartella> [--v15]  motore: tempo, RAM, CPU, annullamento (--v15 = scanner 1.5)
  python benchmarks/bench.py backend <cartella>         MapperBackend offscreen: scansione, ricerca, espandi/comprimi,
                                                        blocchi dell'event loop
Ogni comando stampa una riga JSON / Each command prints one JSON line.
"""
import ctypes
import json
import os
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tests'))


class _Counters(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD),
                ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
                ('QuotaPeakPagedPoolUsage', ctypes.c_size_t), ('QuotaPagedPoolUsage', ctypes.c_size_t),
                ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t), ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t)]


_kernel32, _psapi = ctypes.WinDLL('kernel32'), ctypes.WinDLL('psapi')
_kernel32.GetCurrentProcess.restype = wintypes.HANDLE
_psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Counters), wintypes.DWORD]


def memory_mb():
    """(working set attuale, picco) in MB / (current working set, peak) in MB."""
    counters = _Counters()
    counters.cb = ctypes.sizeof(_Counters)
    _psapi.GetProcessMemoryInfo(_kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
    return counters.WorkingSetSize / 2**20, counters.PeakWorkingSetSize / 2**20


def generate(count, root):
    """Ogni cartella: 18 file vuoti e 2 sottocartelle, 10 estensioni / Each folder: 18 empty files, 2 subfolders."""
    extensions = ['.txt', '.md', '.py', '.json', '.png', '.jpg', '.pdf', '.docx', '.csv', '']
    os.makedirs(root, exist_ok=True)
    made, pending, folder_id, started = 0, [root], 0, time.perf_counter()
    while made < count and pending:
        folder = pending.pop(0)
        for i in range(18):
            if made >= count:
                break
            open(os.path.join(folder, f'f{folder_id}_{i}{extensions[(folder_id + i) % 10]}'), 'x').close()
            made += 1
        for j in range(2):
            if made >= count:
                break
            sub = os.path.join(folder, f'd{j}')
            os.mkdir(sub)
            pending.append(sub)
            made += 1
        folder_id += 1
    return dict(created=made, seconds=round(time.perf_counter() - started, 1))


def engine(root, v15=False):
    if v15:
        import reference_scanner_v15 as scanner
        def run(cancel=None):
            if cancel is None:
                scanner.count_items(root)
            return scanner.snapshot(root, cancel)[0]
    else:
        from mapper_core import scan
        def run(cancel=None):
            return scan(root, cancel=cancel)
    base, _ = memory_mb()
    cpu, started = time.process_time(), time.perf_counter()
    result = run()
    wall = time.perf_counter() - started
    current, peak = memory_mb()
    items = len(result)
    out = dict(engine='1.5' if v15 else '2.0-core', items=items, seconds=round(wall, 3),
               items_per_s=int(items / wall), cpu_percent_one_core=round(100 * (time.process_time() - cpu) / wall),
               ram_peak_mb=round(peak), ram_retained_mb=round(current - base),
               bytes_per_item=int((current - base) * 2**20 / max(items, 1)))
    del result
    cancel = threading.Event()
    worker = threading.Thread(target=run, args=(cancel,))
    worker.start()
    time.sleep(max(0.05, wall * 0.3))
    stop = time.perf_counter()
    cancel.set()
    worker.join()
    out['cancel_ms'] = round((time.perf_counter() - stop) * 1000, 1)
    return out


def backend(root):
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    import tempfile
    from PySide6.QtCore import QElapsedTimer, QEventLoop, QTimer
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication(sys.argv)  # noqa: F841
    from backend import MapperBackend
    b = MapperBackend(config_path=os.path.join(tempfile.mkdtemp(), 'config.json'))
    out, stalls = {}, []
    clock = QElapsedTimer()
    clock.start()
    last = [clock.elapsed()]

    def tick():
        now = clock.elapsed()
        stalls.append(now - last[0])
        last[0] = now
    probe = QTimer()
    probe.timeout.connect(tick)
    probe.start(5)

    def wait(predicate, timeout=600):
        loop, started = QEventLoop(), time.perf_counter()
        while not predicate() and time.perf_counter() - started < timeout:
            loop.processEvents(QEventLoop.AllEvents, 20)

    def phase(name, start, done):
        stalls.clear()
        last[0] = clock.elapsed()
        started = time.perf_counter()
        start()
        wait(done)
        out[f'{name}_s'] = round(time.perf_counter() - started, 3)
        out[f'{name}_max_stall_ms'] = max(stalls, default=0)

    phase('scan', lambda: b.openFolder(root), lambda: b.state['scanned'] and not b.state['busy'] and b.state['shown'] > 0)
    out['items'] = b.state['total']
    top = b.state['shown']
    phase('search', lambda: b.setQuery('f1_'), lambda: b.state['shown'] != top)
    b.clearFilters()
    wait(lambda: b.state['shown'] == top, 60)
    phase('expand_all', lambda: b.expandAll(True), lambda: b.state['shown'] == b.state['total'])
    phase('collapse_all', lambda: b.expandAll(False), lambda: b.state['shown'] == top)
    out['process_peak_ram_mb'] = round(memory_mb()[1])
    b.shutdown()
    return out


if __name__ == '__main__':
    command = sys.argv[1]
    if command == 'gen':
        result = generate(int(sys.argv[2]), sys.argv[3])
    elif command == 'engine':
        result = engine(sys.argv[2], v15='--v15' in sys.argv)
    else:
        result = backend(sys.argv[2])
    print(json.dumps(result))
