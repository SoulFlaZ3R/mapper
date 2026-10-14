# mapper-cli — command line

`mapper-cli.exe` uses the same engine as the Mapper window, without opening any window and without Qt
(about 8 MB). It works in PowerShell, `cmd`, scheduled tasks and CI pipelines. From the source code:
`python src/mapper_cli.py …` (no PySide6 needed).

Results go to **stdout** (UTF-8) or to a file with `-o`; messages go to **stderr**, so pipes stay clean.
Files are written atomically: an interrupted command never leaves a half-written file.

## Commands

| Command | What it does |
| --- | --- |
| `scan FOLDER` | Maps a folder and prints a JSON summary: counts, total size, extensions, excluded items, unreadable items |
| `export FOLDER` | Maps and exports: `-f txt` (default, same tree as the app), `md`, `json`, `csv` |
| `snapshot FOLDER` | Saves the state of a folder as a snapshot (JSON); `--hashes` adds the SHA-256 of every file |
| `diff BEFORE AFTER` | Compares a snapshot with another snapshot or with a folder as it is now; `-f json` (default), `md`, `csv` |
| `validate FILE` | Checks that a snapshot file is valid and prints a JSON report |

Options shared by `scan`, `export`, `snapshot` and `diff` (when AFTER is a folder):

| Option | Meaning |
| --- | --- |
| `--exclude PATTERN` | `.gitignore`-style pattern, repeatable (see [formats.md](formats.md#exclusion-patterns)) |
| `--exclude-from FILE` | File with one pattern per line (`#` comments allowed) |
| `--skip-technical` | Skip `.git`, `node_modules`, `__pycache__`, `.venv`, … |
| `--levels N` | Map only N levels (1 = the folder's direct content) |
| `--strict` | Exit code 5 if some items could not be read |
| `-o, --out FILE` | Write to a file instead of stdout (`export`, `snapshot`, `diff`) |
| `--hide-paths` | No absolute path in the output |
| `-q` / `-v` / `--log-json` | Only errors / progress details / stderr messages as JSON lines |

`export` also accepts `--subtree RELATIVE` (one folder only) and `--no-metadata`. `scan` accepts `--pretty`.

## Exit codes

| Code | Meaning |
| ---: | --- |
| 0 | Success (`diff`: no differences) |
| 1 | `diff`: differences found |
| 2 | Wrong usage (unknown command or option, invalid value) |
| 3 | Invalid input: not a folder, invalid snapshot, invalid pattern, output path is a folder |
| 4 | Read or write error (file missing, folder of the output missing, disk error) |
| 5 | `--strict`: some items could not be read |
| 130 | Interrupted (Ctrl+C) |

## Examples (PowerShell)

```powershell
# Summary of a project folder, without technical folders
mapper-cli scan D:\Work\Project --skip-technical | ConvertFrom-Json

# Tree in Markdown for documentation or a coding agent, without absolute paths
mapper-cli export D:\Work\Project -f md --skip-technical --hide-paths -o project-map.md

# Before/after an installation
mapper-cli snapshot "C:\Program Files\App" -o before.json --hashes
# … install or update the software …
mapper-cli diff before.json "C:\Program Files\App" -f md -o changes.md
if ($LASTEXITCODE -eq 1) { "Something changed" }

# In a pipeline: fail if a deployment folder differs from the expected state
mapper-cli diff expected.json \\server\share\app -q
exit $LASTEXITCODE

# Check a snapshot received from someone else
mapper-cli validate received.json
```

## Encoding

Output is always UTF-8. PowerShell 7 reads it correctly. In Windows PowerShell 5.1, either run
`[Console]::OutputEncoding = [Text.Encoding]::UTF8` before piping names with accents or other alphabets,
or write to a file with `-o` and read it with `Get-Content -Encoding utf8`.

## Logs

`--log-json` writes one JSON object per line on stderr:

```json
{"time": "2026-10-14T08:11:50.381Z", "level": "info", "event": "not_readable", "message": "not readable (access_denied): D:\\Work\\locked", "path": "D:\\Work\\locked", "reason": "access_denied"}
```

Events: `scan_start`, `scan_progress`, `scan_done` (with `-v`), `not_readable`, `hashing`, `verify` (with `-v`),
`compared`, `saved`, `failed` (with `code`), `interrupted`, `io_error`. The CLI never connects to the network
and stores nothing: no telemetry, no configuration files.
