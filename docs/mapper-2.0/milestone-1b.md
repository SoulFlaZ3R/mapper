# Mapper 2.0 — Milestone 1B: esclusioni ed export engine

Data: 14/10/2026 · Branch: `feature/mapper-2.0` · Riferimento: [fase-0-audit.md](fase-0-audit.md) (P0-6, P1-1).

## Cosa è stato fatto

| Backlog | Modifica | File |
| --- | --- | --- |
| P0-6 | Esclusioni in stile `.gitignore` (sottoinsieme documentato) e preset "cartelle tecniche"; limite di livelli da mappare; conteggio di esclusi e cartelle oltre il limite nello stato | `src/mapper_core/filters.py`, `walker.py`, `src/backend.py` |
| P1-1 | Export engine a generatori di righe: TXT (identico alla 1.5), Markdown, JSON `mapper-tree` v1, CSV anti formula-injection; tutta la mappa o una cartella; opzioni "nascondi percorsi completi" e "dimensioni e date"; scrittura atomica annullabile, anche oltre 260 caratteri | `src/mapper_core/export.py`, `model.py` |
| UI | Finestra Esporta con formato, opzioni e anteprima; voce "Esporta questa cartella…" nel menu; finestra "Esclusioni e livelli…" dalle Impostazioni; nuove traduzioni nelle 5 lingue | `src/qml/Main.qml`, `src/Languages/*.json` |
| Doc | Formati e regole dei modelli | `docs/formats.md` |

## Criteri di accettazione

| Criterio | Esito | Evidenza |
| --- | --- | --- |
| TXT legacy identico | ✔ | `test_txt_is_the_1_5_map_and_supports_subtrees`, `test_write_is_atomic_bom_crlf_and_long_paths` |
| JSON valido, versionato, ordine deterministico, percorsi relativi | ✔ | `test_json_schema_paths_and_metadata` |
| Nessun percorso assoluto con "nascondi percorsi" | ✔ | `test_json_subtree_redaction_and_no_metadata`, `test_markdown_document`, `test_export_preview_formats_and_folder_detection` |
| CSV sicuro per i fogli di calcolo | ✔ | `test_csv_is_safe_for_spreadsheets` (file `=SUM(A1).csv`) |
| Unicode ed escape Markdown | ✔ | nomi `Résumé \`v2\`.md`, `md_code`/`md_text` |
| Scrittura atomica e annullabile | ✔ | destinazione intatta e nessun file temporaneo dopo l'annullamento |
| Export di una sola cartella | ✔ | TXT, JSON e backend (`test_save_export_writes_the_chosen_format`) |
| Semantica delle esclusioni | ✔ | 4 test di tabella (nomi a qualsiasi profondità, ancoraggio, `**`, `!`, classi, escape) |
| Esclusioni e livelli applicati e salvati | ✔ | `test_scan_options_exclude_limit_and_persist`, config non valida → valori predefiniti |
| Invio nel campo dei modelli va a capo (non chiude la finestra) | ✔ | verifica con eventi tastiera reali |
| Test | ✔ | 68 test unitari + smoke QML (tutti i formati e le nuove finestre); copertura core 96 % |
| Exe | ✔ | build, smoke test senza avvisi Qt, nessun dato personale |

## Misure (100 000 elementi, stessa macchina)

| Operazione | Tempo | Dimensione |
| --- | ---: | ---: |
| Scansione senza / con 16 regole di esclusione | 1,9 s / 1,4 s | — |
| Export TXT | 0,1 s | 8,0 MB |
| Export Markdown | 0,3 s | 8,0 MB |
| Export JSON | 2,1 s | 19,6 MB |
| Export CSV | 1,6 s | 9,0 MB |

Gli export girano in un thread: l'interfaccia resta reattiva e il salvataggio si può annullare.

## Limiti noti

- Testi delle esportazioni (intestazioni Markdown) in inglese, per stabilità e uso con strumenti esterni.
- CSV con separatore virgola: Excel in italiano può richiedere *Dati → Da testo/CSV* per separare le colonne.
- La redazione nasconde i percorsi assoluti, non i nomi degli elementi (eventuale P2).
- Esclusioni senza file `.gitignore` letti dal disco (una sola lista di regole).

## Prossimo passo: Milestone 2

Snapshot (formato basato su `mapper-tree`, con validazione di input manipolati o enormi) e directory diff:
aggiunti, rimossi, modificati (metadati vs contenuto via hash facoltativo), rename probabili, export
del confronto e vista Compare nell'interfaccia.
