# Architecture

Mapper is split into a core without Qt, shared by the window and the command line, and a thin Qt layer.

```text
             ┌──────────────────────┐        ┌──────────────────────┐
             │ Mapper.exe (window)  │        │ mapper-cli.exe       │
             │ src/mapper.py        │        │ src/mapper_cli.py    │
             │ src/qml/Main.qml     │        │ (no Qt)              │
             │ src/backend.py       │        │                      │
             └──────────┬───────────┘        └──────────┬───────────┘
                        └──────────────┬────────────────┘
                              src/mapper_core (no Qt)
        walker · model · filters · export · snapshot · diff · fsops · paths · version
```

## mapper_core

| Module | Role |
| --- | --- |
| `walker.py` | `scan(root, …)`: the only folder traversal, one pass with `os.scandir`, optional metadata (size, date, attributes), exclusions, level limit, progress, cancellation. Errors are collected, never raised |
| `model.py` | `Tree`: the result stored as columns in pre-order (names, parents, subtree ends, levels, kinds, sizes, dates, attributes), about 100–140 bytes per item. Paths, extensions, text lines and folder totals (prefix sums) are computed on demand |
| `paths.py` | `\\?\` extended paths for every system call (paths over 260 characters), `display()` for people, link detection |
| `filters.py` | `.gitignore`-style exclusion rules and the technical-folders preset ([formats.md](formats.md)) |
| `export.py` | TXT (byte-identical to Mapper 1.5), Markdown, JSON `mapper-tree` v1, CSV; line generators written atomically |
| `snapshot.py` | Loads and validates `mapper-tree` JSON files as untrusted input |
| `diff.py` | Compares two trees or snapshots: added, removed, modified (content only with proof), renamed/moved, `mapper-diff` export |
| `fsops.py` | Copy, move and delete that never follow junctions or symbolic links (recreated as links) |
| `version.py` | `VERSION`, the single version number of app, CLI, build and release script |

The core never imports Qt: the CLI test checks that no PySide6 module is loaded, and the CLI exe is
built without Qt (about 7.5 MB).

## Window (Qt)

- `mapper.py` creates the `QGuiApplication` (no QtWidgets), loads fonts, keeps Qt plugins and QML
  modules inside the bundle and loads `qml/Main.qml`.
- `backend.py` adapts the core to QML:
  - `FileModel` shows the visible rows as an `array('i')` of tree indices; roles are computed when
    QML asks for them. Expanding, collapsing and filtering apply minimal row changes, so scroll and
    selection stay where they are.
  - Long work (scan, filters, exports, file actions, snapshots, comparisons) runs in worker threads;
    workers never touch Qt objects and send results through a queue read every 40 ms.
  - File actions check the path when clicked and again right before acting
    ([security.md](security.md)).
  - State goes to QML as one map (`backend.state`) with one change signal; status messages are
    translation keys, re-translated when the language changes.
- `Main.qml` holds the interface: palettes (light, dark, blue, red, system), shared components
  (`SoftButton`, `SoftDialog`, `SoftMenu` …), the explorer, overview chart, dialogs and menus.

## Command line

`mapper_cli.py` parses the arguments, calls the same core functions as the window and maps results
and errors to documented exit codes ([cli.md](cli.md)).

## Data formats

JSON `mapper-tree` v1 (maps and snapshots) and `mapper-diff` v1 (comparisons) are versioned; a new
major version is introduced only for breaking changes ([formats.md](formats.md)).

## Tests

| Suite | What it covers |
| --- | --- |
| `test_core`, `test_export`, `test_diff` | Core: 1.5-identical text map (against the frozen 1.5 scanner), links, long paths, denied folders, Unicode, cancellation, exclusions, formats, snapshots, comparison |
| `test_backend` | Qt adapter: model updates, search, file actions, preferences, comparison |
| `test_cli` | Real `mapper-cli` processes: outputs, exit codes, UTF-8, no Qt |
| `test_security` | Security regressions (programs, Explorer, plugin isolation, logs, pinned supply chain) |
| `test_i18n`, `test_accessibility`, `test_release` | Translations, WCAG contrast, release script |
| `smoke_ui.py` | The real QML window: every dialog and menu, themes, search, export, virtualization |
