# Mapper 2.0 — Milestone 2: snapshot e confronto

Data: 14/10/2026 · Branch: `feature/mapper-2.0` · Riferimento: [fase-0-audit.md](fase-0-audit.md) (P1-2, P1-3, parte di P1-5).

## Cosa è stato fatto

| Parte | Modifica | File |
| --- | --- | --- |
| Snapshot | Export JSON `mapper-tree` con metadati e impronte SHA-256 facoltative (lette solo su richiesta, annullabili) | `src/mapper_core/export.py` |
| Validazione | Caricamento rigoroso di file potenzialmente ostili: formato e versione, percorsi solo relativi (niente unità, `/` iniziale, `..`, `\`, caratteri vietati), tipi e dimensioni, duplicati senza distinzione di maiuscole, `NaN`, JSON annidato, limiti di 1 GB e 5 milioni di voci; lettura riga per riga a memoria contenuta | `src/mapper_core/snapshot.py` |
| Confronto | Aggiunti, rimossi, modificati (contenuto provato da dimensione o hash; "solo date" altrimenti), cambio tipo, rinomine/spostamenti di cartelle e file solo per corrispondenze uniche con criterio dichiarato; verifica mirata che rilegge solo i file dubbi | `src/mapper_core/diff.py` |
| Export confronto | JSON `mapper-diff` v1, Markdown, CSV anti formula-injection, opzione "nascondi percorsi" | `src/mapper_core/diff.py` |
| App | Pulsante *Confronta* (salva snapshot, con impronte, confronta con la mappa, confronta due snapshot, ultimo confronto); finestra Confronto con filtri per categoria, ricerca, spiegazione di ogni differenza, *Mostra nell'albero*, esportazione | `src/backend.py`, `src/qml/Main.qml`, traduzioni |

## Criteri di accettazione

| Criterio della specifica | Esito | Evidenza |
| --- | --- | --- |
| Creazione e caricamento snapshot | ✔ | `test_canonical_reformatted_and_bom_files_load`, test backend |
| Aggiunti, rimossi, modificati | ✔ | `test_real_folder_snapshot_and_targeted_verification` su una cartella reale |
| Mai "modificato nel contenuto" per la sola data | ✔ | `test_dates_alone_never_mean_content` |
| Distinzione metadati / contenuto verificato con hash | ✔ | `detail` + `verified` in ogni modifica |
| Rinomine probabili con criteri espliciti, nessuna ipotesi su casi ambigui | ✔ | `test_ambiguous_renames_are_not_guessed`, `test_folder_moves_need_a_unique_non_empty_signature` |
| Hash facoltativi senza letture massive | ✔ | verifica mirata: rilegge 2 file su 8 nel test reale |
| Export JSON/Markdown/CSV del confronto | ✔ | `DiffExportTests`, test backend |
| Snapshot manipolati rifiutati | ✔ | `test_hostile_or_broken_files_are_rejected` (19 casi), `test_size_limits` |
| UI con filtri e navigazione | ✔ | smoke QML con confronto reale e cattura della finestra |
| Test | ✔ | 81 test unitari + smoke; copertura core 97 % (`diff.py` 100 %) |
| Exe | ✔ | build, smoke senza avvisi Qt, nessun dato personale |

## Misure (100 000 elementi)

| Operazione | Tempo |
| --- | ---: |
| Salvataggio snapshot (senza impronte) | 1,6 s |
| Caricamento e validazione | 1,0 s |
| Stato attuale dalla mappa | 0,3 s |
| Confronto | 0,15 s |

## Limiti noti

- Un file modificato senza cambiare dimensione né data si riconosce solo con le impronte su entrambi i lati
  (o sul lato salvato più la verifica mirata, se la data è cambiata).
- Le date delle cartelle sono ignorate (cambiano a ogni modifica del contenuto, già elencata).
- Le rinomine "per dimensione e data" sono probabili, non certe: lo dichiara sia l'interfaccia sia l'export.
- Snapshot riformattati a mano accettati fino a 64 MB (quelli scritti da Mapper non hanno questo limite).

## Prossimo passo: Milestone 3

CLI headless (`mapper scan | export | snapshot | diff | validate`) che usa lo stesso core, con exit code
documentati e output JSON, distribuita come `mapper-cli.exe`.
