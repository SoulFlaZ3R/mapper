# Mapper 2.0 — Milestone 5: sicurezza, test e preparazione al rilascio

Data: 14/10/2026 · Branch: `feature/mapper-2.0` · Riferimento: [fase-0-audit.md](fase-0-audit.md) (S1–S12, P1-7, P2-3).

## Cosa è stato fatto

| Parte | Modifica | File |
| --- | --- | --- |
| Programmi | *Apri* su `.exe`, `.bat`, `.cmd`, `.ps1`, `.vbs`, `.js`, `.msi`, `.lnk` … chiede conferma (finestra *Eseguire questo programma?*); documenti e cartelle si aprono subito | `src/backend.py`, `src/qml/Main.qml`, `src/Languages/*.json` |
| Esplora risorse | Avviato con il percorso assoluto nella cartella di Windows (`GetSystemWindowsDirectoryW`): un `explorer.exe` lasciato accanto a Mapper o nella cartella corrente non parte mai | `src/backend.py` |
| Plugin e moduli Qt | Qt metteva la cartella dell'exe (es. Download) **in cima** ai percorsi dei moduli QML e tra quelli dei plugin: ora solo il pacchetto. Il plugin di piattaforma riceve la cartella come argomento (non come variabile d'ambiente, che passerebbe ai programmi aperti da Mapper); `--smoke-test` esce con 1 se la cartella dell'exe è ancora nei percorsi | `src/mapper.py` |
| Log | Il log degli errori di avvio sostituisce la cartella utente (con il nome) con `%USERPROFILE%` | `src/mapper.py`, `src/backend.py` |
| Dipendenze bloccate | `build/requirements-build.txt` (PySide6, PyInstaller) e `build/requirements-tools.txt` (ruff, pip-audit, cyclonedx-bom): versioni esatte e hash SHA-256, generati con `uv` | `build/requirements-*.in/.txt` |
| CI | Azioni fissate per SHA (Node 24), Python 3.12.10 (l'ultima 3.12 con installer per Windows: la prima prova su GitHub ha rifiutato 3.12.14), nessun permesso di base, checkout senza token; installazione con `--require-hashes`; `ruff` (errori, bug, regole di sicurezza Bandit); `pip-audit --strict`; SBOM CycloneDX attestato e pubblicato | `.github/workflows/build-and-sign.yml`, `ruff.toml` |
| Test di sicurezza | 8 nuovi test (programmi, Esplora risorse, moduli QML, log, azioni fissate, lock con hash) + smoke (dialogo e isolamento plugin) | `tests/test_security.py`, `tests/smoke_ui.py` |
| Doc | Sicurezza e privacy (rischio → protezione → test), politica di segnalazione, architettura, benchmark; README IT/EN con sezioni Sicurezza, Documentazione, Roadmap | `docs/security.md`, `SECURITY.md`, `docs/architecture.md`, `docs/benchmarks.md`, `README*.md`, `CHANGELOG.md`, `portable/README.txt` |

## Revisione di sicurezza (Fase 6)

| Punto della specifica | Esito | Evidenza |
| --- | --- | --- |
| Path traversal | ✔ (M1A) | `test_path_and_name_validation`, `test_run_outside_the_mapped_folder_is_refused` |
| Symlink e junction | ✔ (M1A) | `test_copy_never_follows_a_looping_junction`, `test_duplicate_folder_with_a_looping_junction_is_safe` |
| TOCTOU | ✔ (M1A) | `test_path_swapped_for_a_junction_after_the_click_is_refused` |
| Operazioni distruttive | ✔ | solo Cestino, conferma, niente sovrascritture; **nuovo**: conferma prima di eseguire programmi |
| Permessi | ✔ | cartelle negate elencate, nessun privilegio amministrativo (`asInvoker`) |
| Dati sensibili nei log | ✔ **nuovo** | `test_startup_log_hides_the_user_folder` |
| CSV formula injection | ✔ (M1B) | `test_csv_is_safe_for_spreadsheets` |
| JSON non validi o enormi, snapshot manipolati | ✔ (M2) | `test_hostile_or_broken_files_are_rejected`, `test_size_limits` |
| Uso di subprocess | ✔ **nuovo** | `test_explorer_is_started_by_absolute_path`; ruff `S603/S607` senza eccezioni nel codice dell'app |
| Dipendenze vulnerabili | ✔ **nuovo** | `pip-audit --strict`: nessuna vulnerabilità nota (14/10/2026), blocca la build se ne compare una |
| Risorse QML da origini non attendibili | ✔ **nuovo** (difesa in profondità) | `test_qml_imports_only_from_bundle_and_resources`, smoke, `Mapper.exe --smoke-test` |

Nota onesta sui moduli QML: ho verificato che la cartella dell'exe era nei percorsi di ricerca (prima posizione),
ma un attacco reale con un modulo finto (`QtQuick`, `QtQuick.Layouts`, `QtQuick.Dialogs`) **non** è riuscito
nemmeno senza la correzione: Qt 6.12 usa comunque i moduli inclusi. La modifica è quindi una protezione
in più, non la chiusura di una falla dimostrata. L'exe con il modulo finto accanto parte normalmente.

## CI/CD (Fase 8)

| Richiesta | Esito | Evidenza |
| --- | --- | --- |
| Linting e analisi statica | ✔ | `ruff check`: 0 problemi (prima: 2 import inutili nei test, 1 `zip` senza `strict`; i 11 avvisi "logging" erano falsi positivi del logger della CLI) |
| Audit delle dipendenze | ✔ | `pip-audit` su lock della build e degli strumenti: nessuna vulnerabilità nota |
| Dipendenze bloccate | ✔ | lock installati con `--require-hashes` in ambienti puliti; `test_ci_installs_only_locked_hashed_packages` |
| SBOM | ✔ | `Mapper-sbom.cdx.json` (CycloneDX 1.6, 13 componenti, metadati Mapper/MIT) |
| Build riproducibili "per quanto possibile" | parziale | dipendenze, Python e azioni fissati; due build PyInstaller dello stesso codice **non** sono identiche bit per bit (archivio interno diverso): documentato |
| SHA-256, attestazioni | ✔ | per entrambi gli exe e per l'SBOM |
| Firma Authenticode | ✖ | non disponibile (serve un certificato; SignPath gratuito per progetti open source va richiesto) |
| Release notes automatiche | ✔ | sezione del CHANGELOG (`release.py notes`); simulata la 2.0.0: Added/Changed/Security, link di confronto v1.5.0…v2.0.0 |
| Distribuzione portable senza privilegi | ✔ | `asInvoker`, nessuna installazione |

Prove locali della pipeline: installazione dai lock in due ambienti puliti (`.venv-build`, `.venv-tools`),
98 test + smoke in quell'ambiente, build con PyInstaller dal lock, poi gli stessi passi PowerShell del workflow
(smoke GUI, smoke CLI, SBOM, ruff, audit): tutti superati. Il workflow su GitHub **non** è ancora stato eseguito
con queste modifiche (il branch non è pubblicato).

Exe dall'ambiente pulito: `Mapper.exe` 34,2 MB (dal vecchio ambiente di sviluppo 32,4 MB: la differenza
segnalata nell'audit, TD10, dipendeva dall'ambiente), `mapper-cli.exe` 7,4 MB. Nessun dato personale negli exe.

## Test

98 test unitari (erano 90) + smoke dell'interfaccia, tutti superati sia nel vecchio ambiente sia in quello pulito.

## Limiti noti

- Exe non firmato: SmartScreen continua ad avvisare.
- Build non riproducibili bit per bit (limite di PyInstaller).
- Gli avvisi di sicurezza di Qt non sono nel database letto da `pip-audit`: vanno controllati a mano quando si aggiorna PySide6.
- `Main.qml` resta un file unico; nessuna prova con lettori di schermo reali.
- Benchmark non in CI (i server condivisi di GitHub variano troppo).
- Fase 7 (MCP/agenti AI): non implementata, come previsto dalla specifica (prima la valutazione); l'export
  Markdown/JSON, le esclusioni, l'opzione "nascondi percorsi" e la CLI sono già utilizzabili da strumenti esterni.

## Preparazione al rilascio 2.0.0

Pronto lato codice. Passi che richiedono il tuo OK, in ordine:

1. Pubblicare il branch e avviare **Run workflow** (prova a secco su GitHub, nessuna release).
2. Unire `feature/mapper-2.0` in `main`.
3. `build/release.py major` → versione **2.0.0** (titoli README, CHANGELOG, commit e tag locali).
4. Ricompilare e provare gli exe, poi `git push origin main` e `git push origin v2.0.0` (pubblica la release).
5. Caricare `Mapper.exe` e `mapper-cli.exe` della release su VirusTotal (a mano).
