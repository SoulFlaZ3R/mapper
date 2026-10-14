# Benchmarks

`benchmarks/bench.py` measures Mapper on synthetic folders that are always the same, so versions can be
compared. Results depend on the disk, antivirus and CPU: **compare only numbers taken on the same machine**.

## Run

```powershell
python benchmarks/bench.py gen 100000 D:\bench\100k     # deterministic tree: 18 empty files and 2 subfolders per folder
python benchmarks/bench.py engine D:\bench\100k         # core: time, memory, CPU, cancellation
python benchmarks/bench.py engine D:\bench\100k --v15   # same with the frozen Mapper 1.5 scanner
python benchmarks/bench.py backend D:\bench\100k        # whole app offscreen: scan, search, expand/collapse, UI pauses
```

Each command prints one JSON line. Run every measurement three times with a warm file cache and keep the median.

## Results: 1.5 → 2.0

Measured on 14/10/2026 on the development machine (Windows 11), warm cache, median of 3 runs.

Core (`engine`; 1.5 = count pass + scan pass):

| Items | Time 1.5 | Time 2.0 | Memory per item | Peak memory | Cancel reaction |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 10,000 | 0.43–0.61 s | 0.12–0.15 s | 1,173 → ~140 B | 28 → 19 MB | 1–2 ms → 0.2 ms |
| 100,000 | 4.9 s | 1.2–1.3 s | 1,220 → ~120 B | 134 → 31 MB | 13 ms → 1 ms |
| 1,000,000 | 57–60 s | 15–19 s | 1,282 → ~103 B | 1,247 → 124 MB | 140–175 ms → 6–8 ms |

Whole app (`backend`):

| Items | Mapping | Peak process memory | Longest UI pause |
| ---: | ---: | ---: | ---: |
| 10,000 | 0.65 → 0.27 s | 52 → 41 MB | 8 → 9 ms |
| 100,000 | 6.3 → 1.9–2.2 s | 185 → 58 MB | 22 → 15 ms |
| 1,000,000 | 64.3 → 25.5–26.7 s | 1,558 → 224 MB | 91 → 17 ms |

Search, *expand all* and *collapse all* stay under 0.3 s at one million items.

Benchmarks are not part of CI: shared GitHub runners vary too much for reliable timing. Run them
before and after changes to the scanner or the tree model.
