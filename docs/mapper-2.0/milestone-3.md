# Mapper 2.0 — Milestone 3: riga di comando

Data: 14/10/2026 · Branch: `feature/mapper-2.0` · Riferimento: [fase-0-audit.md](fase-0-audit.md) (P1-4).

## Cosa è stato fatto

| Parte | Modifica | File |
| --- | --- | --- |
| CLI | `scan`, `export`, `snapshot`, `diff`, `validate`; esclusioni, livelli, `--strict`, `--hide-paths`; risultati su stdout in UTF-8 o su file (atomico); messaggi su stderr, anche come righe JSON (`--log-json`); `-q`/`-v` | `src/mapper_cli.py` |
| Nessun Qt | La CLI importa solo `mapper_core`; la versione è stata spostata in `src/mapper_core/version.py` (unica fonte per app, CLI, build e `release.py`) | `src/mapper_core/version.py`, `src/backend.py`, `build/release.py` |
| Eseguibile | `mapper-cli.exe` (console, ~7,6 MB, senza Qt) dallo stesso `mapper.spec`, con informazioni di versione e manifest `longPathAware` | `build/mapper.spec`, `build/build.bat`, `.gitignore` |
| CI/rilascio | Smoke test della CLI (versione, scansione, snapshot, convalida, diff senza differenze); artifact, attestazione, `.sha256` e pubblicazione per entrambi gli eseguibili; la prova a secco li cancella entrambi | `.github/workflows/build-and-sign.yml` |
| Doc | Comandi, opzioni, codici di uscita, esempi PowerShell, codifica, log | `docs/cli.md`, README IT/EN, `portable/README.txt` |

## Codici di uscita

0 ok (diff: nessuna differenza) · 1 differenze trovate · 2 uso errato · 3 input non valido · 4 lettura/scrittura ·
5 elementi non leggibili con `--strict` · 130 interrotto.

## Criteri di accettazione

| Criterio della specifica | Esito | Evidenza |
| --- | --- | --- |
| Stesso motore della GUI, nessuna logica duplicata | ✔ | la CLI chiama solo `mapper_core` (scan, export, snapshot, diff) |
| Nessuna sessione grafica, nessun Qt | ✔ | `test_real_process_utf8_and_no_qt` (nessun modulo PySide6/shiboken6 caricato); exe senza Qt |
| Supporto PowerShell | ✔ | `ConvertFrom-Json` su scan/diff, `$LASTEXITCODE`, nomi Unicode (prove manuali con l'exe) |
| Exit code documentati | ✔ | `test_snapshot_validate_and_diff_exit_codes`, `test_strict_mode_and_json_logs`, `test_version_and_usage` |
| Output JSON machine-readable | ✔ | scan, validate, export/diff `-f json` |
| Logging strutturato, quiet/verbose | ✔ | `--log-json` (righe JSON), `-q` senza output su stderr |
| Gestione sicura dei percorsi | ✔ | cartella inesistente → 3, output su una cartella → 3, cartella di output mancante → 4, sottocartella fuori mappa → 3, scrittura atomica |
| Niente servizi, telemetria o rete | ✔ | nessun accesso di rete, nessun file di configurazione |
| Test | ✔ | 87 test unitari + smoke; copertura CLI 96 %, core 97 % |
| Exe | ✔ | entrambi compilati; smoke GUI senza avvisi, passo CI della CLI simulato in locale; nessun dato personale |

## Limiti noti

- In Windows PowerShell 5.1 i nomi con accenti passati in pipe richiedono `[Console]::OutputEncoding = [Text.Encoding]::UTF8`
  oppure `-o file` (PowerShell 7 funziona senza impostazioni).
- Un secondo eseguibile significa un secondo file da controllare su VirusTotal a ogni rilascio.
- Il nuovo passo CI della CLI è stato provato in locale; la prima esecuzione su GitHub avverrà al prossimo push.

## Prossimo passo: Milestone 4

Rifinitura dell'interfaccia: pannello dettagli (dimensione, date, attributi), breadcrumb, stati vuoti ed errori,
accessibilità, suddivisione di `Main.qml` in componenti.
