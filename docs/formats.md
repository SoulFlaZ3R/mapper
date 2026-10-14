# Mapper export formats

All formats list the mapped items in the same order as the tree: folders first, then files,
case-insensitive, depth first. Excluded items and items that could not be read are not listed
(unreadable ones appear in the `errors` section of JSON and Markdown). Exports can cover the whole
map or a single folder (*Export this folder…*).

| Format | Use | Encoding |
| --- | --- | --- |
| TXT | Unicode tree, identical to Mapper 1.5 | UTF-8, Windows line endings |
| Markdown | Documentation, README files, context for coding agents | UTF-8 |
| JSON | Structured data for scripts and tools (versioned schema) | UTF-8 |
| CSV | Spreadsheets (Excel, LibreOffice) | UTF-8 with BOM, CRLF |

Files are written to a temporary file in the same folder and then swapped in, so an interrupted or
failed export never leaves a half-written file. Paths longer than 260 characters are supported.

## Options

| Option | Effect |
| --- | --- |
| Hide full paths | No absolute path in the output: JSON `root.path` is `null`, Markdown shows *hidden*. Paths of entries are always relative. |
| Include sizes and dates | Adds `size` (bytes, files only), `modified` (UTC, ISO 8601) and Windows `attributes`. |
| Only the folder | Exports one folder: its name becomes the root, depths start again from 0. |

## JSON — `mapper-tree` version 1

```json
{
  "format": "mapper-tree",
  "version": 1,
  "generator": {"name": "Mapper", "version": "1.5.0"},
  "generated": "2026-10-14T08:30:00Z",
  "root": {"name": "Project", "path": "D:\\Work\\Project"},
  "options": {"subtree": false, "redacted": false, "metadata": true, "hashes": false, "levels": null, "excluded_patterns": [".git/"]},
  "summary": {"items": 3, "folders": 1, "files": 2, "links": 0, "bytes": 2056, "excluded": 1, "errors": 0, "complete": true},
  "entries": [
    {"path": "src", "name": "src", "type": "dir", "depth": 0, "modified": "2026-10-13T22:26:06.824Z", "attributes": []},
    {"path": "src/main.py", "name": "main.py", "type": "file", "depth": 1, "extension": ".py", "size": 8, "modified": "2023-11-14T22:13:20.000Z", "attributes": ["archive"]},
    {"path": "README.md", "name": "README.md", "type": "file", "depth": 0, "extension": ".md", "size": 2048, "modified": "2023-11-14T22:13:20.000Z", "attributes": ["archive"]}
  ],
  "errors": []
}
```

| Field | Meaning |
| --- | --- |
| `format`, `version` | Always `mapper-tree` and an integer. A new major version means fields changed meaning; new optional fields do not change the version. |
| `root.path` | Absolute path, or `null` when paths are hidden. |
| `options.levels` | Levels limit used while mapping (`null` = all). |
| `options.excluded_patterns` | Exclusion rules used while mapping. |
| `summary.bytes` | Total size of the files (`null` without metadata). |
| `summary.excluded` | Items skipped by the exclusion rules (`null` for a single-folder export). |
| `summary.complete` | `false` if the mapping was cancelled. |
| `entries[].path` | Relative to the exported root, always with `/`. |
| `entries[].type` | `dir`, `file` or `link` (symbolic link or NTFS junction, never followed). |
| `entries[].depth` | 0 for items directly inside the exported root. |
| `entries[].extension` | Lower-case, files only (`""` when there is none). |
| `entries[].sha256` | Only in snapshots with fingerprints: SHA-256 of the file, `null` if it could not be read. |
| `entries[].attributes` | Any of `readonly`, `hidden`, `system`, `archive`, `reparse_point`, `compressed`, `offline`, `encrypted`. |
| `errors[]` | `{path, reason}`; reason is `access_denied`, `not_found`, `path_too_long`, `depth_limit` or `error`. |

Each entry is on its own line, so very large exports can be processed line by line.

## Snapshots and comparison

A **snapshot** is a JSON export of the whole map with sizes and dates (*Compare → Save snapshot…*).
*Save snapshot with fingerprints* also stores the SHA-256 of every file (`"sha256"` in each file entry,
`options.hashes: true`): it reads every file once, so it is slower, but later comparisons can prove whether
content changed. Any `mapper-tree` JSON export with metadata can be used as a snapshot.

Loading a snapshot validates it strictly, because the file may come from anywhere: the `format` and
`version` must match, every path must be relative (no drive, no leading `/`, no `..`, no `\`, no control
characters or characters Windows forbids), types and sizes must be valid, a path may appear only once
(ignoring letter case), `NaN`/`Infinity` and deeply nested JSON are refused, and files over 1 GB or 5 million
entries are rejected. A file written by Mapper is read line by line (low memory); a reformatted file is
accepted up to 64 MB.

The comparison (*Compare a snapshot with this map…* or *Compare two snapshots…*) lists:

| Change | Rule |
| --- | --- |
| added / removed | present on one side only |
| modified · content | proven: different size, or different SHA-256 |
| modified · dates only | dates differ but the content was not proven to change (with fingerprints: same content) |
| modified · type | a file became a folder or the opposite |
| renamed or moved · folder | a removed and an added folder with exactly the same content (relative paths, types, sizes) |
| renamed or moved · hash | a removed and an added file with the same SHA-256 |
| renamed or moved · size and date | probable: same size (> 0), same date and same extension |

Renames are reported only when the match is unique; otherwise the items stay added and removed. Dates are
compared with a 2 ms tolerance. Folder dates are ignored (they change whenever their content changes).
When a snapshot with fingerprints is compared with the current map, Mapper re-reads only the files whose
size is the same but whose date changed, to confirm whether their content changed. A file edited without
changing size or date cannot be detected without fingerprints on both sides.

### JSON — `mapper-diff` version 1

```json
{
  "format": "mapper-diff",
  "version": 1,
  "generator": {"name": "Mapper", "version": "1.5.0"},
  "generated": "2026-10-15T09:00:00Z",
  "old": {"name": "Project", "path": "D:\\Work\\Project", "generated": "2026-10-14T08:30:00Z"},
  "new": {"name": "Project", "path": "D:\\Work\\Project", "generated": null},
  "options": {"hashes_used": true, "mtime_tolerance_s": 0.002, "redacted": false},
  "summary": {"added": 1, "removed": 0, "modified": 1, "renamed": 1, "unchanged": 40, "content": 1, "metadata": 0, "complete": true},
  "changes": [
    {"change": "added", "path": "notes.md", "type": "file", "new_size": 12, "new_modified": "2026-10-15T08:59:00.000Z"},
    {"change": "modified", "path": "main.py", "type": "file", "detail": "content", "verified": true, "old_size": 8, "old_modified": "2026-10-14T08:00:00.000Z", "new_size": 8, "new_modified": "2026-10-15T08:00:00.000Z"},
    {"change": "renamed", "path": "archive", "type": "dir", "old_path": "docs/old", "detail": "folder", "verified": false}
  ]
}
```

`generated` of a side is `null` when that side is the current map. CSV columns: `change, path, old_path,
type, detail, verified, old_size, new_size, old_modified, new_modified` (formula-safe, like the map CSV).

## CSV

Columns: `path, name, type, depth, extension, size, modified, attributes`. Attributes are letters:
R read-only, H hidden, S system, A archive, L reparse point, C compressed, O offline, E encrypted.

Cells that a spreadsheet would run as a formula (starting with `=`, `+`, `-`, `@`, tab or carriage
return) get a leading `'`, as recommended by OWASP against CSV formula injection. A file named
`=SUM(A1).csv` is therefore exported as `'=SUM(A1).csv`.

## Markdown

A title, a summary table (path, generation time, content, total size, exclusions, levels), the tree
in a fenced `text` block (the fence is longer than any run of backticks in the names) and a table of
file types. Unreadable items are listed at the end.

## Exclusion patterns

One pattern per line, `.gitignore` style:

| Pattern | Matches |
| --- | --- |
| `*.log` | any file or folder named `*.log`, at any depth |
| `node_modules/` | folders only |
| `/build` | `build` directly inside the mapped folder only |
| `docs/**/*.tmp` | `.tmp` files anywhere below `docs` |
| `!keep.log` | re-includes an item excluded by an earlier rule |
| `#notes`, `\#notes` | a comment, and a name that really starts with `#` |

Differences from Git: matching ignores letter case (like Windows), only one list of rules is used
(nested `.gitignore` files on disk are not read), and — as in Git — an excluded folder is not read,
so `!` cannot bring back something inside it. *Skip technical folders* adds `.git/`, `.svn/`, `.hg/`,
`node_modules/`, `__pycache__/`, `.venv/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.tox/`,
`.idea/`, `.vs/`, `$RECYCLE.BIN/`, `System Volume Information/` and `Thumbs.db`.
