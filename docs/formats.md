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
  "options": {"subtree": false, "redacted": false, "metadata": true, "levels": null, "excluded_patterns": [".git/"]},
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
| `entries[].attributes` | Any of `readonly`, `hidden`, `system`, `archive`, `reparse_point`, `compressed`, `offline`, `encrypted`. |
| `errors[]` | `{path, reason}`; reason is `access_denied`, `not_found`, `path_too_long`, `depth_limit` or `error`. |

Each entry is on its own line, so very large exports can be processed line by line.

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
