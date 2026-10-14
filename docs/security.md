# Security and privacy

Mapper is a local desktop app: it reads folders the user chooses and, on request, renames, copies,
moves or deletes items inside the mapped folder. This page describes what it protects against, how
each protection is tested, what it stores, and how releases are built and can be verified.

To report a vulnerability, see [SECURITY.md](../SECURITY.md).

## What Mapper never does

- **No network access**: no updates, telemetry, analytics or crash reports. The only links are the
  repository and guide links in Settings, opened in the browser when clicked.
- **No permanent deletion**: *Delete* moves items to the Windows Recycle Bin after a confirmation.
  If the Recycle Bin cannot take the item (for example on some network drives) the action fails
  with an error; nothing is deleted.
- **No administrator rights**: the exe asks for none and works as a normal user.
- **No overwriting**: copies get a unique name (`name - copy`, `name - copy (2)` …); moves refuse an
  existing destination.

## Protections and their tests

Every row is checked by automated tests that run on each release build (`tests/`, unittest).

| Risk | Protection | Tests |
| --- | --- | --- |
| Actions outside the mapped folder (`..`, other drives, links) | Every file action resolves links, `..` and short 8.3 names and must stay inside the mapped folder; the mapped folder itself cannot be deleted | `test_backend.test_path_and_name_validation`, `test_folder_cannot_be_pasted_into_itself`, `test_security.test_run_outside_the_mapped_folder_is_refused` |
| Invalid or dangerous names | Names with `\ / : * ? " < > \|`, control characters, trailing dot/space, `.`/`..` and reserved names (`CON`, `NUL`, `COM1` …) are refused | `test_backend.test_path_and_name_validation` |
| Junction / symlink abuse | Links are shown as links and never followed while mapping, copying, duplicating, moving or deleting; copies recreate them as links | `test_core.test_junctions_are_links_not_traversed`, `test_copy_never_follows_a_looping_junction`, `test_remove_tree_keeps_junction_targets`, `test_backend.test_duplicate_folder_with_a_looping_junction_is_safe` |
| Race between the click and the action (TOCTOU) | The path is checked when clicked and again right before the action runs; a folder swapped for a junction is refused | `test_backend.test_path_swapped_for_a_junction_after_the_click_is_refused` |
| Destructive actions | Recycle Bin only, confirmation dialog, no overwrite, a cross-drive move deletes the source only after a complete copy | `test_backend.test_cut_paste_moves_and_refuses_overwrite`, `test_path_and_name_validation` |
| Running a program by mistake | *Open* on a program or script (`.exe`, `.bat`, `.cmd`, `.ps1`, `.vbs`, `.js`, `.msi`, `.lnk` …) asks for confirmation first; documents and folders open directly | `test_security.test_programs_ask_before_running`, `test_program_extensions`, smoke test (`runDialog`) |
| `subprocess` misuse / binary planting | The only process Mapper starts is Explorer (*Show in Explorer*), with its absolute path in the Windows folder, list arguments and no shell: an `explorer.exe` dropped next to Mapper or in the current folder is never started | `test_security.test_explorer_is_started_by_absolute_path` |
| Qt plugins or QML modules from untrusted folders | Qt plugins and QML modules load only from the files bundled in the exe, never from the folder that contains `Mapper.exe` (for example Downloads) | `test_security.test_qml_imports_only_from_bundle_and_resources`, `smoke_ui.py` and `Mapper.exe --smoke-test` (both fail if the exe folder is searched) |
| Unreadable folders, long paths | Errors are collected and listed (access denied, not found, path too long, too deep); paths over 260 characters work | `test_core.test_denied_folder_is_reported_and_scan_goes_on`, `test_long_paths_are_read`, `test_backend.test_actions_work_on_paths_longer_than_260_characters` |
| CSV formula injection | Cells starting with `=`, `+`, `-`, `@`, tab or carriage return are prefixed with `'` | `test_export.test_csv_is_safe_for_spreadsheets`, `test_diff.test_csv_and_markdown` |
| Hostile or huge snapshot/JSON files | Strict validation: only relative paths without `..`, drive letters or control characters; type, size and entry limits (1 GB, 5 M entries); no duplicates, NaN or deep nesting | `test_diff.test_hostile_or_broken_files_are_rejected`, `test_size_limits`, `test_backend.test_compare_two_snapshot_files_and_reject_bad_ones`, `test_cli.test_snapshot_validate_and_diff_exit_codes` |
| Half-written files | Exports and snapshots are written to a temporary file and renamed when complete; cancelling leaves the old file intact | `test_export.test_write_is_atomic_bom_crlf_and_long_paths`, `test_backend.test_cancel_does_not_publish_partial_snapshot` |
| Personal data in logs | The startup error log replaces the user folder (which contains the user name) with `%USERPROFILE%` | `test_security.test_startup_log_hides_the_user_folder` |
| Vulnerable or swapped dependencies | See [Supply chain](#supply-chain) | `test_security.test_actions_are_pinned_by_commit`, `test_ci_installs_only_locked_hashed_packages`, CI audit |

## Privacy

Mapper keeps everything on the computer:

| What | Where | Content |
| --- | --- | --- |
| Preferences | `%APPDATA%\Mapper\config.json`, or `config.json` next to the exe if it exists (USB use) | theme, language, reduced motion, exclusion rules, level limit, the last 6 folders opened |
| Startup error log | `%APPDATA%\Mapper\mapper-startup.log` (only after a startup failure) | technical error details, user folder hidden |
| Exports and snapshots | only where you save them | names, and if chosen full paths, sizes, dates and SHA-256 fingerprints |

Exports, snapshots and comparisons can contain folder and file names of other people or projects.
Use **Hide full paths** in the export window (or `--hide-paths` on the command line) before sharing
them. Mapper does not anonymize file names.

## Supply chain

How a release is built (`.github/workflows/build-and-sign.yml`, started only by a version tag):

- **Locked dependencies**: `build/requirements-build.txt` (PySide6, PyInstaller and their
  dependencies) and `build/requirements-tools.txt` (ruff, pip-audit, cyclonedx-bom) list exact
  versions with SHA-256 hashes; CI installs them with `--require-hashes`, so a changed file stops
  the build. The tools never enter the exe.
- **Pinned actions and Python**: every GitHub Action is pinned to a commit SHA (a tag can be moved,
  a SHA cannot), Python is pinned to 3.12.14, the checkout keeps no token and the job has only the
  permissions it uses.
- **Checks before the build**: `ruff` (errors, common bugs and Bandit-style security rules, see
  `ruff.toml`), `pip-audit --strict` on the build dependencies (known vulnerabilities from the
  PyPI/OSV database), then unit tests.
- **Checks after the build**: smoke test of both exes (`Mapper.exe --smoke-test` also verifies the
  plugin isolation), command-line smoke test.
- **Published with each release**: SHA-256 of each exe, a GitHub build-provenance attestation of
  both exes and of the SBOM, and `Mapper-sbom.cdx.json` (CycloneDX component list).

Verify a download (PowerShell, in the download folder):

```powershell
Get-FileHash Mapper.exe -Algorithm SHA256        # compare with the value in the release text
gh attestation verify Mapper.exe --repo SoulFlaZ3R/mapper
```

### Maintenance

- **Update the locked dependencies** (for example a new PySide6): edit `build/requirements-build.in`
  (or `requirements-tools.in`) and regenerate with [uv](https://docs.astral.sh/uv/):

  ```powershell
  uv pip compile build/requirements-build.in --generate-hashes --python-version 3.12 --python-platform windows --no-header -o build/requirements-build.txt
  uv pip compile build/requirements-tools.in --generate-hashes --python-version 3.12 --python-platform windows --no-header --exclude-newer <date a week ago> -o build/requirements-tools.txt
  ```

- **Update an action**: read the release notes and `action.yml` of the new version (`runs.using`
  must be `node24` or `composite`), then take the commit of its tag with
  `git ls-remote --tags https://github.com/<owner>/<repo>` (for annotated tags use the `^{}` line)
  and replace both the SHA and the `# vX.Y.Z` comment.
- **Same environment locally**: `uv venv .venv-build --python 3.12` then
  `uv pip install --python .venv-build/Scripts/python.exe --require-hashes -r build/requirements-build.txt`
  (the same for `.venv-tools`). `.venv-*` folders are ignored by git.

## Known limits

- **Not code-signed**: Windows SmartScreen warns about an unknown publisher. The SHA-256 and the
  attestation prove where the file comes from; Authenticode signing (for example SignPath for open
  source projects) is prepared in the workflow but not active.
- **Builds are not bit-for-bit reproducible**: two PyInstaller builds from the same sources and locked
  dependencies differ in the packed archive. The attestation links each published exe to the exact
  commit and workflow run that built it.
- **Qt advisories**: Qt security advisories are published by qt.io, not in the PyPI/OSV database that
  `pip-audit` reads; they must be checked by hand when updating PySide6.
- **Open runs programs after confirmation**: once confirmed, Windows runs the program with the
  user's rights, exactly as a double click in Explorer would (SmartScreen and antivirus still apply).
- Whoever can write in the folder that contains `Mapper.exe` can also replace the exe itself: keep it
  in a folder only you can change.
