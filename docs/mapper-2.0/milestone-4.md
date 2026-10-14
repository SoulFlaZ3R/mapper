# Mapper 2.0 — Milestone 4: rifinitura dell'interfaccia

Data: 14/10/2026 · Branch: `feature/mapper-2.0` · Riferimento: [fase-0-audit.md](fase-0-audit.md) (P2).

## Cosa è stato fatto

| Parte | Modifica | File |
| --- | --- | --- |
| Totali delle cartelle | `Tree.totals(i)` restituisce file, cartelle e byte di un sottoalbero in tempo costante (somme prefisse costruite una volta nel thread di scansione) | `src/mapper_core/model.py`, `src/backend.py` |
| Dettagli | Slot `details(path)`: tipo, dimensione, totali, data di modifica, attributi e percorso a passi (radice + cartelle antenate) | `src/backend.py` |
| Barra della selezione | Sotto l'albero: percorso cliccabile (clic su un passo = apri quella cartella, la radice torna in cima), nome, dettagli e copia percorso; il suggerimento fisso appare solo senza selezione | `src/qml/Main.qml` |
| Stati vuoti | In mappatura (con il numero di elementi trovati), benvenuto, nessun risultato, cartella vuota, tutto escluso (pulsante *Modifica esclusioni*), cartella non leggibile (pulsante *Mostra dettagli*) | `src/qml/Main.qml` |
| Accessibilità | Righe dell'albero con descrizione per i lettori di schermo (cartella, collegamento o estensione); barra della selezione con ruolo *barra di stato* e testo completo; testo secondario più scuro (chiaro) e più chiaro (scuro): contrasto minimo da 3,75 a **4,62:1** | `src/qml/Main.qml`, `tests/test_accessibility.py` |
| Traduzioni | 15 nuove chiavi in 5 lingue (195 chiavi ciascuna) | `src/Languages/*.json` |
| Doc | Funzionalità README IT/EN, CHANGELOG, screenshot rigenerati | `README*.md`, `CHANGELOG.md`, `docs/screenshots/` |

## Criteri di accettazione

| Criterio della specifica | Esito | Evidenza |
| --- | --- | --- |
| Pannello dettagli (dimensione, date, attributi) | ✔ | `test_details_and_breadcrumb_of_the_selection`; smoke: dettagli che iniziano con `File · 0 B` |
| Breadcrumb | ✔ | smoke: *Workspace › Documents › nested-report.txt*; screenshot del README |
| Totali di una cartella senza rileggere il disco | ✔ | `test_folder_totals_in_constant_time` (anche senza metadati: byte = 0) |
| Stati vuoti ed errori chiari | ✔ | smoke: titolo *This folder is empty* su una cartella vuota; schermata nessun risultato già coperta |
| Contrasto WCAG AA ≥ 4,5:1 | ✔ | `test_every_theme_meets_wcag_aa_for_normal_text` su 4 temi × 12 coppie testo/sfondo |
| Lettori di schermo | ✔ (parziale) | nomi e descrizioni accessibili su righe e barra; non provato con NVDA/Narratore |
| Nessuna regressione | ✔ | 90 test unitari + smoke UI; mappa TXT identica alla 1.5 |
| Exe | ✔ | entrambi compilati; `--smoke-test` senza avvisi; nessun dato personale |

## Limiti noti

- `Main.qml` non è stato diviso in componenti (resta un file unico di ~1 600 righe): la divisione è un
  cambiamento ampio senza vantaggi per l'utente e va fatta con calma, dopo il rilascio 2.0.
- Non c'è un "annulla" per le operazioni sui file oltre al Cestino di Windows.
- L'accessibilità non è stata provata con un lettore di schermo reale.

## Prossimo passo: Milestone 5

Sicurezza e preparazione al rilascio: controlli CI (lint, audit delle dipendenze, SBOM, azioni fissate per
hash), revisione finale della sicurezza, note di rilascio 2.0.
