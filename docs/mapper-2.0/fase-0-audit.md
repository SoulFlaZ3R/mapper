# Mapper 2.0 — Fase 0: audit e baseline

Data: 14/10/2026 · Base analizzata: `main` @ `fafb022` (v1.5.0) · Nessun sorgente modificato.
Ambiente di misura: Windows 11 Pro 10.0.26300, 16 core logici, SSD NVMe, Python 3.12.14, PySide6 6.12.0, PyInstaller 6.22.3.

Legenda evidenze: **[M]** misurato in questo audit · **[T]** verificato con un test/esperimento ·
**[C]** dedotto dalla lettura del codice (non ancora dimostrato con un test).

---

## 1. Executive technical assessment

Mapper 1.5 è una base piccola e ordinata (≈ 860 righe Python di prodotto + 1 115 righe QML) con scelte
giuste per la sua dimensione: una sola visita del filesystem condivisa da albero ed export, worker che non
toccano oggetti Qt, export atomico, eliminazione solo nel Cestino, 29 test unitari più uno smoke test del QML
reale, CI con attestazione di provenienza.

Per diventare la 2.0 descritta nella specifica (Explore → Map → Analyze → Compare → Export → Automate) mancano
le fondamenta dati, non solo funzioni:

1. **Il modello dati non contiene metadati** (dimensione, date, attributi): senza questi non esistono export
   strutturati utili né diff tra snapshot. È il prerequisito di quasi tutto il backlog.
2. **Il motore di scansione ha un tetto di scala** [M]: 1 milione di elementi = ~55 s e ~1,25 GB di RAM solo
   per lo scanner, perché ogni elemento è un `dict` con 7 stringhe (~1,3 KB/elemento) e l'albero viene letto
   due volte (conteggio per la % + visita). Il 42 % del tempo della visita è `os.path.relpath`.
3. **Gli errori sono silenziosi** [T]: cartelle senza permessi e percorsi oltre 260 caratteri vengono saltati
   senza alcuna segnalazione; l'utente vede una mappa incompleta come se fosse completa.
4. **Un bug di sicurezza/robustezza reale** [T]: *Duplica* (e potenzialmente *Sposta* tra volumi) segue le
   junction NTFS. Una junction che punta a una cartella antenata produce una copia ricorsiva che cresce fino
   al limite dei percorsi e si interrompe con errore lasciando una copia parziale; una junction verso una
   cartella esterna grande ne copierebbe l'intero contenuto dentro la radice.
5. **Backend e QML monolitici**: `MapperBackend` (≈ 520 istruzioni) unisce modello, job, filtri, azioni sui
   file, preferenze e traduzioni; `Main.qml` contiene tutta l'interfaccia. Va bene oggi, ma la CLI e il diff
   richiedono di separare un *core* senza Qt.

Raccomandazione: nessuna riscrittura. Estrarre un pacchetto `core` puro (modello dati, motore, filtri,
export, snapshot/diff) usato sia dalla GUI sia da una CLI; lasciare `backend.py` come adattatore Qt.
Prima milestone: **motore + modello dati + errori + long path + fix junction**, poi **export engine**.

---

## 2. Architettura attuale

```text
mapper.py ──► QGuiApplication + QQmlApplicationEngine ──► qml/Main.qml (UI intera)
     │                                   ▲  property state (QVariantMap), signals
     ▼                                   │
backend.py  MapperBackend(QObject) ──────┘
  ├─ FileModel(QAbstractListModel)       righe visibili = list[dict]
  ├─ _work(job, done): threading.Thread  → queue.Queue → QTimer 40 ms (_drain) sul thread UI
  ├─ scan(): count_items() + snapshot()  (scanner.py, puro, senza Qt)
  ├─ _filter(): thread per ogni modifica di ricerca/espansione, revision counter
  ├─ fileAction(): rinomina, nuovo, incolla (copy/move), duplica, Cestino (QFile.moveToTrash)
  ├─ exportMap(): scrittura atomica (tempfile + os.replace)
  └─ preferenze JSON (%APPDATA%\Mapper o accanto all'exe), traduzioni JSON (5 lingue)
build/mapper.spec ─► PyInstaller onefile (filtro Qt + controllo dipendenze DLL)
.github/workflows ─► tag v*: check versione/CHANGELOG → test → build → smoke → attestazione → SHA-256 → release
```

Flussi verificati nel codice:

| Flusso | Implementazione | Note |
| --- | --- | --- |
| Scansione | `scan()` → worker: `count_items` (visita completa) poi `snapshot` (seconda visita) | progress per percentuale; risultato pubblicato solo a fine visita |
| Navigazione | `toggle/expandAll` → `_filter` ricostruisce le righe visibili da tutti i record | `FileModel.replace` calcola prefisso/suffisso comuni per non perdere scroll |
| Ricerca | debounce 160 ms → `_filter` scorre tutti i record con `casefold` | nessun indice; nuovo thread a ogni battuta |
| Export | righe Unicode già calcolate in `snapshot` (`_lines`) → TXT atomico | anteprima limitata a 1 200 righe |
| Azioni file | `_checked()` (risoluzione percorso dentro la radice) nel thread UI, operazione nel worker | dopo l'azione: nuova scansione completa |
| Thread/segnali | worker → `queue.Queue` → `QTimer` 40 ms (max 32 messaggi per tick) | i worker non toccano oggetti Qt ✔ |

## 3. Architettura target (proposta, da approvare)

```text
src/
  mapper_core/              Python puro, nessun import Qt, testabile e usato da GUI e CLI
    model.py                Entry (dataclass slots / tuple), ScanResult, ScanError, ScanOptions
    walker.py               visita iterativa, annullamento cooperativo, errori raccolti, long path (\\?\),
                            reparse point, profondità massima, metadati opzionali (stat già in DirEntry)
    filters.py              esclusioni stile .gitignore (sottoinsieme documentato) + preset
    export/                 txt (legacy), markdown, json (schema versionato), csv (anti formula-injection)
    snapshot.py / diff.py   formato snapshot versionato, validazione, confronto, rename probabili
    io.py                   scrittura atomica, redazione percorsi
  mapper_cli.py             argparse: scan | export | snapshot | diff | validate (exit code documentati)
  mapper.py / backend.py    GUI: solo adattatori Qt (modello, job, segnali)
  qml/                      Main.qml diviso in componenti (Explore, Compare, Export, Settings)
```

Principi: il core non conosce Qt; la GUI non contiene logica di dominio; ogni formato ha uno *schema
version*; nessuna nuova dipendenza runtime senza approvazione (vedi §10).

---

## 4. Technical debt assessment

| ID | Debito | Evidenza | Impatto |
| --- | --- | --- | --- |
| TD1 | Doppia visita del disco (`count_items` + `snapshot`) solo per la % di avanzamento | [M] conteggio = 20–25 % del tempo totale | lentezza su dischi lenti/di rete |
| TD2 | Un `dict` di 7 stringhe per elemento + righe di testo dell'albero sempre in memoria | [M] ~1 290 byte/elemento trattenuti | 1 M elementi ≈ 1,25 GB solo scanner |
| TD3 | `os.path.relpath` per ogni elemento | [M] profilo: 5,1 s su 12,1 s di visita (dataset 100k, 50 % cartelle) | CPU sprecata |
| TD4 | Errori `OSError` ingoiati (scandir) | [T] cartella negata e path > 260 non segnalati | mappe incomplete senza avviso |
| TD5 | `MapperBackend` multiruolo (~520 istruzioni) | [C] | difficile riuso da CLI, test lenti |
| TD6 | `Main.qml` monolitico (1 115 righe) | [C] | ogni nuova vista aumenta il rischio di regressioni |
| TD7 | `_filter` copia ogni record (`dict(record, expanded=…)`) e lancia un thread per ogni battuta; `FileModel.indexOf` lineare | [C] + misure §6 | costo O(n) a ogni espansione/ricerca |
| TD8 | Dopo ogni azione sui file: nuova scansione completa | [C] | lento su alberi grandi |
| TD9 | `MAX_DEPTH = 500` scarta i livelli più profondi senza segnalarlo | [C] | caso raro, ma silenzioso |
| TD10 | Ambiente di sviluppo locale divergente dai requisiti (matplotlib, numpy, customtkinter, Pillow, WebEngine residui) | [M] | build locale ≠ build CI (anche: exe CI 35 MB vs locale 32 MB) |
| TD11 | `requirements.txt` non bloccato (`PySide6>=6.8,<7`), PyInstaller senza versione in CI | [C] | build non riproducibili |

## 5. Security risk register

Valutazione: P = probabilità, I = impatto (B/M/A). Stato: Aperto se non mitigato oggi.

| ID | Rischio | Evidenza | P | I | Stato / mitigazione proposta |
| --- | --- | --- | --- | --- | --- |
| S1 | **Duplica/Sposta seguono junction NTFS** (`shutil.copytree(symlinks=True)` non tratta le junction come link) | [T] junction ciclica → copia ricorsiva fino al limite path, errore, copia parziale; junction verso l'esterno → copia di contenuti fuori radice | M | A | Aperto. Copia propria che replica junction/symlink come link (o li salta) + test di regressione |
| S2 | TOCTOU: `_checked()` valida nel thread UI, l'operazione avviene dopo nel worker | [C] | B | M | Aperto. Rivalidare nel worker subito prima dell'operazione; operare su percorsi risolti |
| S3 | Errori di accesso nascosti → decisioni su dati incompleti | [T] | A | M | Aperto. Raccogliere `ScanError` (percorso, tipo) e mostrarli |
| S4 | Percorsi lunghi (> 260) non letti: manifest senza `longPathAware`, nessun prefisso `\\?\` | [T] file a 695 caratteri non trovato; con prefisso `\\?\` la visita li trova | A | M | Aperto. `longPathAware` nel manifest + prefisso esteso nel motore |
| S5 | CSV formula injection | n/d (nessun CSV oggi) | — | M | Da prevenire nell'export CSV (prefisso `'` per `= + - @` e tab/CR iniziali) |
| S6 | Snapshot/JSON manipolati o enormi | n/d (nessun import oggi) | — | M | Validazione schema, limiti dimensione/profondità, nessun `eval` |
| S7 | `subprocess.Popen(f'explorer /select,"{target}"')` | [C] stringa, non `shell=True`; `"` non ammesso nei nomi Windows | B | B | Accettabile; passare a lista argomenti per pulizia |
| S8 | Dati sensibili nei log | [C] solo `mapper-startup.log` (traceback, può contenere percorsi) | B | B | Documentare; opzione di redazione nei log futuri |
| S9 | Caricamento QML/plugin da origini non attendibili | [M] import path include la cartella dell'exe ma con priorità più bassa dei moduli inclusi; QML caricato solo dal pacchetto | B | M | Accettabile; valutare `QML_DISABLE_DISK_CACHE`/import path esplicito |
| S10 | Dipendenze vulnerabili | [M] OSV: 0 vulnerabilità note per PySide6/shiboken6 6.12.0, PyInstaller 6.22.3 (le CVE di Qt sono pubblicate da qt.io, non da OSV PyPI: limite) | B | M | Aggiungere audit automatico in CI |
| S11 | Operazioni distruttive | [C] eliminazione solo Cestino ✔, conferma ✔, radice protetta ✔, copie senza sovrascrittura ✔ | B | A | Già mitigato; aggiungere test negativi su junction/symlink |
| S12 | Supply chain build | [C] azioni GitHub fissate per major tag (non SHA), dipendenze non bloccate | B | A | Pin per SHA + lock con hash + SBOM |

## 6. Performance baseline

Dataset sintetici deterministici (`bench.py gen`): ogni cartella ha 18 file vuoti e 2 sottocartelle
(~10 % cartelle), 10 estensioni. Cache del filesystem calda (2ª e 3ª esecuzione), mediana di 3 esecuzioni.
I valori dipendono da disco, antivirus e CPU: servono come **confronto relativo** tra versioni sulla stessa macchina.

### 6.1 Motore (scanner.py, senza Qt) [M]

| Elementi | Conteggio % | Visita | Totale | Elementi/s | CPU (1 core) | RAM picco | RAM/elemento | Annullamento |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 000 | 0,09 s | 0,36 s | 0,45 s | ~22 000 | ~95 % | 27 MB | ~1,2 KB | < 1 ms |
| 100 000 | 0,89 s | 3,73 s | 4,62 s | ~21 600 | ~95 % | 133 MB | ~1,2 KB | ~8 ms |
| 1 000 000 | 11,6 s | 43,8 s | 55,2 s | ~18 100 | ~97 % | 1 246 MB | ~1,3 KB | ~90 ms |

Osservazioni: crescita lineare; un solo core usato; con un dataset più ricco di cartelle (50 %) il profilo
mostra 3,9 s in `scandir` e 5,1 s in `relpath` su 12,1 s.

### 6.2 Applicazione (MapperBackend offscreen, senza rendering QML) [M]

| Elementi | Scansione fino alle prime righe | Blocco max UI | Ricerca (incl. debounce 160 ms) | Espandi tutto | Comprimi tutto | RAM picco processo |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 000 | 0,65 s | 8 ms | 0,19 s | 0,05 s | 0,05 s | 52 MB |
| 100 000 | 6,3 s | 22 ms | 0,19 s | 0,05 s | 0,06 s | 185 MB |
| 1 000 000 | 64,3 s | 91 ms | 0,28 s | 0,70 s | 0,24 s | 1 558 MB |

Lettura: l'architettura worker + coda mantiene l'interfaccia reattiva (nessun blocco > 100 ms nemmeno a
1 M elementi). I limiti reali sono **tempo di scansione** e **memoria**, non la reattività. Nell'app la
scansione costa ~35 % in più del solo motore (messaggi di avanzamento, filtro iniziale, contesa del GIL).

"Blocco massimo" = intervallo più lungo tra due tick di un timer da 5 ms sul thread dell'interfaccia: misura
quanto l'app resta senza rispondere. Non include il costo di disegno del QML (limite della misura).

## 7. Test coverage assessment [M]

29 test unitari (scanner 5, backend 16, i18n 2, release 6) + smoke test del QML reale: tutti verdi
(anche con TEMP in forma breve 8.3). Copertura istruzioni (coverage.py 7.16, unit + smoke):

| Modulo | Copertura | Non coperto (sintesi) |
| --- | ---: | --- |
| `src/scanner.py` | 90 % | rami `OSError` (permessi negati, path lunghi) |
| `src/backend.py` | 89 % | `openPath`, `showInFolder`, `copyPath/copyMap`, errori Cestino, collisione in rinomina, errori di scrittura config |
| `src/mapper.py` | 52 % | blocco `__main__` (coperto solo dallo smoke test dell'exe in CI) |
| `build/release.py` | 46 % | percorso git reale (`prepare`, `check_repository`) |

Mancano del tutto: test su permessi negati, path lunghi, junction nelle azioni sui file, Unicode nelle azioni,
dataset grandi, prestazioni con soglie, test di sicurezza negativi, test dell'exe con dati.

Verifiche di casi limite eseguite in questo audit [T]:

| Caso | Risultato |
| --- | --- |
| Nomi Unicode (cirillico, CJK, emoji, combinanti, katakana half-width) | ✔ elencati correttamente |
| Percorso di 695 caratteri | ✘ non letto oltre ~287 caratteri, nessun avviso; con radice `\\?\` ✔ |
| Junction ciclica verso la radice | ✔ non attraversata, ma mostrata come **file** (icona e conteggio sbagliati) |
| Junction verso cartella esterna | ✔ non attraversata nella scansione; ✘ attraversata da *Duplica* (S1) |
| Symlink a cartella | non verificabile: creazione richiede privilegio/Developer Mode (limite dell'ambiente) |
| Cartella con lettura negata | ✘ cartella mostrata vuota, nessun errore |
| Percorso UNC (`\\localhost\C$\…`) | ✔ scansione corretta (condivisione amministrativa) |
| `count_items` vs elementi visitati | ✔ coerenti |

---

## 8. Gap analysis rispetto alla specifica 2.0

| Area | Oggi (1.5) | Gap |
| --- | --- | --- |
| Motore | visita iterativa, annullabile, no symlink/junction | metadati, errori, long path, esclusioni, profondità, visita singola, memoria compatta, risultati incrementali |
| Export | TXT albero Unicode | Markdown, JSON versionato, CSV, snapshot, sottoalbero, redazione, schema |
| Snapshot & diff | assente | tutto |
| CLI | assente (exe senza console) | tutto, incluso il packaging di un eseguibile console |
| UX | Explore + Export + Settings, temi/lingue, tastiera | Analyze (dimensioni/date), Compare, pannello dettagli, breadcrumb, stati di errore, filtri combinati |
| Sicurezza | Cestino, conferme, radice protetta, scrittura atomica | S1–S4, validazione input futuri, test negativi |
| CI/CD | test, build, smoke, attestazione, SHA-256, check versione | lint, audit dipendenze, lock con hash, SBOM, pin SHA azioni, benchmark |
| Documentazione | README IT/EN, CHANGELOG | architettura, formati, CLI, benchmark, sicurezza/privacy, roadmap |

## 9. Backlog prioritizzato

**P0 — correttezza, sicurezza, fondamenta**

| ID | Attività | Dipende da | Complessità | Criterio di accettazione |
| --- | --- | --- | --- | --- |
| P0-1 | Fix S1: copia/spostamento che non seguono junction/symlink | — | Bassa | test con junction ciclica ed esterna: nessun contenuto esterno copiato, nessuna ricorsione |
| P0-2 | Rivalidazione dei percorsi nel worker (S2) | — | Bassa | test che sostituisce una cartella con una junction tra click ed esecuzione → operazione rifiutata |
| P0-3 | Modello dati core (`Entry` compatto) + `ScanResult` con errori | — | Media | RAM/elemento ≤ 50 % della baseline su 1M [M]; nessun import Qt nel core |
| P0-4 | Motore: visita singola con progress stimato, long path (`\\?\` + manifest), raccolta errori, junction come "collegamento" (non file) | P0-3 | Media | 1M elementi ≥ 1,5× più veloce della baseline sulla stessa macchina; path 695 caratteri trovato; cartella negata segnalata |
| P0-5 | Metadati opzionali (dimensione, mtime/ctime, attributi) da `DirEntry.stat()` | P0-3 | Bassa | costo aggiuntivo misurato e documentato; test |
| P0-6 | Esclusioni (preset + pattern stile .gitignore, differenze documentate) e profondità massima | P0-4 | Media | suite di casi pattern; esclusioni riflesse in conteggi ed export |

**P1 — funzioni 2.0**

| ID | Attività | Dipende da | Complessità |
| --- | --- | --- | --- |
| P1-1 | Export engine: TXT legacy (identico byte per byte), Markdown, JSON schema v1, CSV sicuro, sottoalbero, redazione percorsi, scrittura atomica | P0-3..6 | Media |
| P1-2 | Snapshot JSON versionato + validazione (limiti dimensione, schema) | P1-1 | Media |
| P1-3 | Diff: aggiunti/rimossi/modificati (metadati vs contenuto via hash opzionale), rename probabili con criteri espliciti, export JSON/MD/CSV | P1-2 | Alta |
| P1-4 | CLI `scan/export/snapshot/diff/validate`, exit code, output JSON, quiet/verbose | P1-1..3 | Media |
| P1-5 | GUI: pannello dettagli, colonne dimensione/data, vista Compare con filtri e navigazione | P1-3 | Alta |
| P1-6 | Filtri/ricerca senza copie per record, aggiornamenti incrementali dopo le azioni (no rescan completo) | P0-3 | Media |
| P1-7 | CI: ruff, pip-audit/OSV, lock con hash, pin SHA azioni, SBOM CycloneDX, benchmark di regressione | — | Media |

**P2 — rifinitura e futuro**

| ID | Attività |
| --- | --- |
| P2-1 | Suddivisione di `Main.qml` in componenti; breadcrumb; stati vuoti/errore; accessibilità (screen reader, contrasto) |
| P2-2 | Hash on-demand (SHA-256) per file selezionati e nel diff |
| P2-3 | Build riproducibile (toolchain bloccata, `SOURCE_DATE_EPOCH`), firma Authenticode quando disponibile (SignPath) |
| P2-4 | Export Markdown ottimizzato per coding agent; valutazione server MCP locale read-only, disattivato di default |
| P2-5 | Pulizia ambiente di sviluppo (TD10) e allineamento build locale/CI |

Dipendenze chiave: P0-3 → P0-4/5/6 → P1-1 → P1-2 → P1-3 → P1-4/P1-5. P0-1, P0-2 e P1-7 sono indipendenti.

## 10. Decisioni che richiedono approvazione

1. **Nuovo pacchetto `mapper_core`** (cambio architetturale, nessuna rottura per l'utente).
2. **Pattern di esclusione**: implementazione interna di un sottoinsieme `.gitignore` (zero dipendenze)
   *oppure* la libreria `pathspec` (MPL-2.0, pura Python, piccola). Raccomando l'implementazione interna
   per la prima milestone, con le differenze documentate.
3. **CLI distribuita come secondo eseguibile console** (`mapper-cli.exe`, dallo stesso spec) — l'exe attuale
   è senza console e non può scrivere su stdout/PowerShell in modo affidabile. Aumenta gli artefatti di
   release e va verificato anche con VirusTotal.
4. **Versione**: le nuove funzioni portano alla 2.0.0 secondo lo schema del progetto (MAJOR dopo 10 funzioni).

## 11. Rischi tecnici e di sicurezza

- Un modello Qt con 1 M righe visibili resta costoso anche con un core efficiente: servirà caricamento
  incrementale/virtuale dell'albero (solo righe visibili), non solo un motore più veloce.
- Le prestazioni reali dipendono da antivirus e dischi di rete: i benchmark vanno confrontati sulla stessa macchina.
- La semantica `.gitignore` completa (negazioni, ancoraggi, `**`) è sottile: rischio di aspettative errate se
  non documentata e testata.
- Più eseguibili e codice di sistema (reparse point, `\\?\`) aumentano la superficie per falsi positivi
  antivirus e per bug specifici di Windows.
- Diff su alberi grandi: memoria O(n) per due snapshot; servirà un confronto ordinato in streaming.

## 12. Piano di test

| Livello | Contenuto | Quando |
| --- | --- | --- |
| Unit core | modello, walker (Unicode, long path, permessi negati, junction, symlink se disponibile, profondità, esclusioni), export (golden file per formato), snapshot (schema, file corrotti/enormi), diff (casi tabellari) | ogni commit |
| Integrazione | backend Qt + core su cartelle temporanee; azioni file con junction (regressione S1/S2) | ogni commit |
| GUI smoke | QML reale, nuove viste, screenshot | ogni commit |
| CLI | exit code, output JSON valido, PowerShell pipeline | ogni commit |
| Prestazioni | `bench.py` 10k/100k in CI (soglie larghe), 1M manuale prima di ogni release | CI + release |
| Sicurezza | test negativi (path traversal, junction, CSV injection, JSON malformato/enorme) | ogni commit |
| Exe | smoke dell'exe, scansione di una cartella demo, VirusTotal | ogni release |

## 13. Proposta della prima milestone implementabile

**Milestone 1A — Motore e fondamenta** (branch `feature/mapper-2.0`, v1.5 come baseline):
P0-1, P0-2, P0-3, P0-4, P0-5 + `bench.py` nel repository (cartella `benchmarks/`).

File coinvolti: nuovo `src/mapper_core/{model,walker}.py`; `src/scanner.py` (diventa adattatore o viene
sostituito mantenendo l'output TXT identico); `src/backend.py` (azioni file, errori di scansione);
`build/app.manifest` (`longPathAware`); `src/qml/Main.qml` + traduzioni (avviso "N elementi non leggibili",
junction mostrate come collegamenti); nuovi test.

Criteri di accettazione misurabili:

- export TXT identico byte per byte alla 1.5 su tutti i dataset di prova;
- 1 M elementi: tempo ≤ 2/3 e RAM ≤ 1/2 della baseline §6.1 sulla stessa macchina;
- percorso > 260 caratteri trovato; cartella negata elencata come errore; junction non attraversate e
  mostrate come collegamenti; *Duplica* con junction ciclica/esterna non copia nulla fuori radice;
- tutti i test esistenti + i nuovi verdi; copertura del core ≥ 90 %.

**Milestone 1B — Export engine ed esclusioni**: P0-6, P1-1.

---

### Appendice — riproducibilità

Script: la misura è ora `benchmarks/bench.py` (Milestone 1A); i casi limite e la riproduzione di S1 sono
diventati test automatici in `tests/test_core.py` e `tests/test_backend.py`. Nota: una prima versione della
misura del backend leggeva il numero di righe prima che il filtro iniziale arrivasse e dava tempi falsi su
"comprimi tutto"; corretta e rieseguita, i valori in §6.2 sono quelli corretti. Comandi:

```powershell
python benchmarks/bench.py gen 100000 <cartella>
python benchmarks/bench.py engine <cartella> --v15
python benchmarks/bench.py backend <cartella>
```
