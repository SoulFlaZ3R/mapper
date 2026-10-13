# Changelog

All notable changes to Mapper are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow the project scheme
(PATCH = fixes, MINOR = new features, MAJOR = after ten features).
The section of each version is the text of its GitHub release.

## [Unreleased]

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
