# Mapper 2.0 — Milestone 1A: motore e fondamenta

Data: 14/10/2026 · Branch: `feature/mapper-2.0` (base: v1.5.0 `fafb022`) · Riferimento: [fase-0-audit.md](fase-0-audit.md) §13.

## Cosa è stato fatto

| Backlog | Modifica | File |
| --- | --- | --- |
| P0-1 | Copia/spostamento sicuri: junction e symlink ricreati come collegamenti, mai seguiti; copia "dentro sé stessa" rifiutata anche tramite junction; spostamento tra unità che non elimina l'origine se un collegamento non è ricreabile | `src/mapper_core/fsops.py`, `src/backend.py` |
| P0-2 | Ricontrollo del percorso nel worker subito prima dell'azione (`error_path_changed`) | `src/backend.py` |
| P0-3 | Modello dati a colonne (`Tree`), senza Qt; righe della lista = indici nell'albero | `src/mapper_core/model.py`, `src/backend.py` |
| P0-4 | Visita singola (avanzamento = elementi trovati), percorsi `\\?\` oltre 260 caratteri, errori raccolti e mostrati, junction come collegamenti, `longPathAware` nel manifest | `src/mapper_core/walker.py`, `paths.py`, `build/app.manifest`, `src/qml/Main.qml` |
| P0-5 | Dimensione, data di modifica e attributi raccolti durante la visita (costo non misurabile) | `src/mapper_core/walker.py` |
| — | Benchmark nel repository | `benchmarks/bench.py` |

Lo scanner 1.5 è conservato, congelato, in `tests/reference_scanner_v15.py`: i test confrontano la mappa
testuale nuova con la sua, riga per riga.

## Criteri di accettazione

| Criterio | Esito | Evidenza |
| --- | --- | --- |
| Export TXT identico byte per byte alla 1.5 | ✔ | `test_core` (3 alberi, incluse junction) e `test_backend` (export completo); dataset 10k e 100k |
| 1 M elementi: tempo ≤ 2/3 della baseline | ✔ ~1/3,6 | 57–60 s → 15–19 s (motore) |
| 1 M elementi: RAM ≤ 1/2 della baseline | ✔ ~1/10 | picco 1 247 MB → 124 MB (motore) |
| Percorso > 260 caratteri trovato | ✔ | `test_long_paths_are_read`, `test_actions_work_on_paths_longer_than_260_characters` |
| Cartella negata segnalata | ✔ | `test_denied_folder_is_reported_and_scan_goes_on`, `test_unreadable_folders_are_reported`, cattura dell'exe |
| Junction non attraversate e mostrate come collegamenti | ✔ | `test_junctions_are_links_not_traversed`, `test_links_are_rows_of_kind_link`, cattura dell'exe |
| *Duplica* con junction ciclica/esterna: nulla copiato fuori radice | ✔ | `test_copy_never_follows_a_looping_junction`, `test_copy_does_not_pull_outside_content`, `test_duplicate_folder_with_a_looping_junction_is_safe` |
| Percorso sostituito dopo il clic → azione rifiutata | ✔ | `test_path_swapped_for_a_junction_after_the_click_is_refused` |
| Tutti i test verdi | ✔ | 51 test unitari + smoke QML; anche con TEMP in forma breve 8.3 |
| Copertura del core ≥ 90 % | ✔ 96 % | coverage.py: fsops 93 %, model 98 %, paths 100 %, walker 96 % |

## Misure (stessa macchina e stessi dataset della Fase 0)

Motore (`benchmarks/bench.py engine`, mediana; 1.5 = conteggio + visita):

| Elementi | 1.5 | 2.0-core | RAM per elemento | Picco RAM | Annullamento |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 10 000 | 0,43–0,61 s | 0,12–0,15 s | 1 173 → ~140 B | 28 → 19 MB | 1–2 ms → 0,2 ms |
| 100 000 | 4,9 s | 1,2–1,3 s | 1 220 → ~120 B | 134 → 31 MB | 13 ms → 1 ms |
| 1 000 000 | 57–60 s | 15–19 s | 1 282 → ~103 B | 1 247 → 124 MB | 140–175 ms → 6–8 ms |

App (`benchmarks/bench.py backend`, MapperBackend offscreen):

| Elementi | Scansione 1.5 → 1A | Picco RAM processo 1.5 → 1A | Blocco max UI 1.5 → 1A |
| ---: | ---: | ---: | ---: |
| 10 000 | 0,65 → 0,27 s | 52 → 41 MB | 8 → 9 ms |
| 100 000 | 6,3 → 1,9–2,2 s | 185 → 58 MB | 22 → 15 ms |
| 1 000 000 | 64,3 → 25,5–26,7 s | 1 558 → 224 MB | 91 → 17 ms |

Ricerca, "espandi tutto" e "comprimi tutto" restano sotto 0,3 s anche a 1 M elementi.

## Cambiamenti visibili

- Durante la mappatura lo stato mostra "N elementi trovati" invece della percentuale (la percentuale
  richiedeva una seconda lettura completa del disco).
- Barra di stato: pulsante "Non leggibili: N" → finestra con percorso e motivo.
- Junction e link simbolici hanno l'icona dei collegamenti e l'etichetta "collegamento".
- Nuove chiavi di traduzione nelle 5 lingue.

## Limiti noti e decisioni

- Symlink reali non creabili in questo ambiente (serve privilegio o Modalità sviluppatore): il ramo
  "symlink non ricreabile" è testato simulando l'errore di Windows.
- Lo spostamento tra unità è testato simulando l'errore `ERROR_NOT_SAME_DEVICE` (una sola unità nei test).
- Il costo del disegno QML con 1 M righe visibili non è misurato (la misura è sul backend offscreen).
- L'eseguibile resta ~32 MB; smoke test dell'exe e controllo dati personali superati.
- Versione invariata (1.5.0): il salto a 2.0.0 avverrà al rilascio delle funzioni 2.0.

## Prossimo passo proposto: Milestone 1B

P0-6 esclusioni (sottoinsieme `.gitignore` documentato, profondità configurabile) e P1-1 export engine
(TXT legacy, Markdown, JSON con schema versionato, CSV protetto da formula injection, sottoalbero,
redazione dei percorsi, scrittura atomica).
