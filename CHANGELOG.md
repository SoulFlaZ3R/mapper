# Changelog

All notable changes to Mapper are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow the project scheme
(PATCH = fixes, MINOR = new features, MAJOR = after ten features).
The section of each version is the text of its GitHub release.

## [Unreleased]

### Added

- Snapshots and comparison: save the state of a folder (optionally with SHA-256 fingerprints) and compare it later with the current map or with another snapshot: added, removed, modified (content vs dates only), renamed or moved files and folders; filter, show in the tree, export as Markdown, JSON (`mapper-diff` schema) or CSV
- Export as Markdown, JSON (versioned `mapper-tree` schema) and CSV besides the text tree, for the whole map or a single folder, with optional sizes and dates and an option to hide full paths ([docs/formats.md](docs/formats.md))
- Exclusions: skip technical folders (`.git`, `node_modules`, …), `.gitignore`-style patterns and a limit on the levels to map
- Folders that cannot be read (access denied, path too long, too deep) are listed: *N not readable* in the status bar opens the list
- Paths longer than 260 characters are mapped and can be renamed, created, copied and moved
- Junctions and symbolic links are shown as links with their own icon instead of as files
- Size, date and attributes are collected during the scan (base for structured exports and comparisons)

### Changed

- New scanning core (`mapper_core`, no Qt): one pass over the disk instead of two, about 3–5× faster and about 9× less memory per item on the benchmark trees; the text map is unchanged byte for byte
- While mapping, the status shows the number of items found instead of a percentage

### Security

- Snapshot files are validated before use (relative paths only, no `..`, size and entry limits, no duplicates, no NaN or deeply nested JSON)
- CSV export neutralizes cells that spreadsheets would run as formulas (`=`, `+`, `-`, `@`)
- *Duplicate* and *Paste* no longer follow junctions: a folder containing a junction to itself was copied into itself until the path limit, and a junction to another folder copied that content into the mapped folder. Links are now recreated as links
- File actions check again, right before running, that the selected item has not been replaced (for example by a junction pointing outside the mapped folder)

## [1.5.0] - 2026-10-14

First public release.

### Added

- Qt Quick/QML interface (PySide6) with one consistent style for buttons, fields, menus, dialogs and tooltips
- Map a folder in one step: browse, drag it onto the window, paste a path or pick a recent folder
- Virtualized tree with expand/collapse all and full keyboard navigation; open folders stay open after refreshes and file actions
- Search as you type across the whole map, with highlighted matches and each result's location; *Show in tree* opens the parent folders and selects the item
- Interactive donut chart and legend of file types: click a type to filter the list
- File actions: open, show in Explorer, copy path, cut/copy/paste, duplicate, new file/folder, rename, delete to the Recycle Bin; copies never overwrite
- Export the map: preview, copy to the clipboard or save as UTF-8 text
- Five themes (light, dark, blue, red, system) and five languages (Italian, English, German, French, Spanish) with live preview
- Preferences and recent folders are saved in `%APPDATA%\Mapper`; a `config.json` next to `Mapper.exe` is used instead only if it already exists (USB stick use)
- Portable `Mapper.exe` (about 32 MB) built by GitHub Actions from the release tag, with a build-provenance attestation and a SHA-256 checksum

### Fixed

- File actions no longer fail as "outside the mapped folder" when the folder path uses Windows 8.3 short names (for example `RUNNER~1`)

[Unreleased]: https://github.com/SoulFlaZ3R/mapper/compare/v1.5.0...HEAD
[1.5.0]: https://github.com/SoulFlaZ3R/mapper/releases/tag/v1.5.0
