# Mapper 1.5

[English](README.md) · **Italiano**

Un'app desktop per Windows per esplorare cartelle, trovare file ed esportare mappe ad albero Unicode.
Python gestisce il filesystem; l'interfaccia è realizzata con **PySide6 + Qt Quick/QML**.

![Esplora di Mapper nel tema scuro](docs/screenshots/03-explorer-dark.png)

## Screenshot

| | |
| --- | --- |
| ![Schermata iniziale con le cartelle recenti](docs/screenshots/01-start.png) | ![Esplora con l'albero aperto, tema chiaro](docs/screenshots/02-explorer-light.png) |
| **Avvio** — sfoglia, trascina una cartella o riapri una recente | **Esplora** — albero espandibile e panoramica dei tipi di file |
| ![Risultati di ricerca con le corrispondenze evidenziate](docs/screenshots/04-search.png) | ![Filtro per tipo di file dalla legenda del grafico](docs/screenshots/05-filter-type.png) |
| **Cerca** — corrispondenze evidenziate, con la posizione di ogni elemento | **Filtra per tipo** — clic sul grafico o sulla legenda |
| ![Menu contestuale con le azioni sui file](docs/screenshots/06-context-menu.png) | ![Finestra Esporta mappa con l'anteprima dell'albero](docs/screenshots/07-export.png) |
| **Azioni** — clic destro o ⋯ per le operazioni sui file | **Esporta mappa** — anteprima, copia o salvataggio come testo |
| ![Impostazioni nel tema blu, in italiano](docs/screenshots/08-settings.png) | |
| **Impostazioni** — cinque temi e cinque lingue, con anteprima dal vivo | |

Gli screenshot sono generati da una cartella dimostrativa con `python build/make_screenshots.py`.

## Come iniziare

Mapper funziona su **Windows 10 e 11**.

### Opzione 1 — Scarica l'app

Quando è disponibile una release, scarica `Mapper.exe` dalla
[pagina Releases](https://github.com/SoulFlaZ3R/mapper/releases) e aprilo con un doppio clic.
Non serve installazione: è un unico file portatile. Ogni release riporta anche il codice SHA-256
e un'attestazione di build di GitHub, per verificare che il file sia stato compilato da questo codice
([come verificarlo](docs/security.md#supply-chain), in inglese), e l'elenco dei componenti (SBOM).

Windows SmartScreen potrebbe avvisare di un editore sconosciuto, perché l'app non è ancora firmata
digitalmente: scegli **Ulteriori informazioni → Esegui comunque**.

### Opzione 2 — Avvialo dal codice sorgente

1. Installa **Python 3.12 o più recente** da [python.org](https://www.python.org/downloads/windows/).
   Durante l'installazione spunta **"Add python.exe to PATH"**.
2. Scarica il codice: in questa pagina clicca **Code → Download ZIP** ed estrai l'archivio, oppure usa Git:

   ```powershell
   git clone https://github.com/SoulFlaZ3R/mapper.git
   cd mapper
   ```

3. Apri PowerShell nella cartella del progetto (in Esplora risorse: **Maiusc + clic destro → Apri finestra di PowerShell qui**)
   e crea un ambiente isolato:

   ```powershell
   py -m venv .venv
   ```

4. Installa le dipendenze (PySide6, qualche centinaio di MB) e avvia Mapper:

   ```powershell
   .venv\Scripts\python -m pip install -r requirements.txt
   .venv\Scripts\python src/mapper.py
   ```

Le volte successive basta l'ultimo comando.

Preferenze e cartelle recenti restano sul tuo computer. L'app le salva nella cartella nascosta
`%APPDATA%\Mapper`, quindi accanto a `Mapper.exe` (per esempio sul Desktop) non compare nessun file.
Per portarle su una chiavetta, crea un `config.json` vuoto accanto a `Mapper.exe`: l'app userà quel file.
Avviando dal codice sorgente sono salvate in `src/config.json`.

## Funzionalità

- **Mappatura in un passo**: Sfoglia, trascina una cartella sulla finestra, incolla un percorso o scegli una cartella recente; la mappatura parte subito
- Albero virtualizzato con espandi/comprimi, espandi tutto/comprimi tutto e navigazione completa da tastiera; le cartelle aperte restano aperte dopo un aggiornamento o un'azione sui file
- **Ricerca mentre scrivi** in tutta la mappa, con le corrispondenze evidenziate e la posizione di ogni risultato; *Mostra nell'albero* apre le cartelle che lo contengono e seleziona l'elemento
- Grafico ad anello interattivo e legenda completa e scorrevole; clicca un tipo di file per filtrare, di nuovo (o sull'etichetta) per togliere il filtro
- **Barra della selezione** sotto l'albero: percorso cliccabile dell'elemento selezionato (clic su un passo per
  andare a quella cartella), dimensione, data e attributi; per le cartelle i file, le sottocartelle e la dimensione totale
- Stati vuoti chiari: cartella vuota, nessun risultato, tutto escluso dalle tue regole (con scorciatoia alle
  regole) oppure cartella non leggibile (con scorciatoia ai dettagli)
- Scansione in background con conteggio dal vivo degli elementi trovati e possibilità di annullare
- Azioni con clic destro (o ⋯): apri, mostra in Esplora risorse, copia percorso, taglia/copia/incolla, duplica, nuovo file/cartella, rinomina, elimina
- Elimina sposta gli elementi nel **Cestino**; le copie non sovrascrivono mai (`nome - copia`, `nome - copia (2)` …); i nomi vengono controllati prima della conferma
- Aprire un programma o uno script (`.exe`, `.bat`, `.ps1`, `.lnk` …) chiede prima conferma, così niente parte per sbaglio
- **Esporta mappa** come albero di testo (TXT), Markdown, JSON o CSV, per tutta la mappa o una cartella (clic destro →
  *Esporta questa cartella…*); dimensioni e date facoltative, opzione per nascondere i percorsi completi, anteprima e copia.
  Il CSV è protetto dalla formula injection. Vedi [docs/formats.md](docs/formats.md)
- **Snapshot e confronto**: salva lo stato di una cartella e più tardi vedi cosa è stato aggiunto, rimosso,
  modificato (contenuto provato da dimensione o impronta SHA-256, le sole date non contano mai) e rinominato o
  spostato; filtra le differenze, aprile nell'albero ed esportale in Markdown, JSON o CSV (pulsante *Confronta*)
- **Riga di comando** (`mapper-cli.exe`): mappa, esporta, salva snapshot, confronta e convalida da PowerShell o
  da una pipeline, con output JSON e codici di uscita documentati — vedi [docs/cli.md](docs/cli.md)
- **Esclusioni**: salta le cartelle tecniche (`.git`, `node_modules`, …), aggiungi modelli in stile `.gitignore`
  e limita i livelli da mappare (Impostazioni → *Esclusioni e livelli…*)
- Cinque temi (chiaro, scuro, blu, rosso, sistema) e cinque lingue (italiano, inglese, tedesco, francese, spagnolo), con anteprima dal vivo nelle Impostazioni
- Uno stile unico e coerente per pulsanti, campi, menu, finestre di dialogo, suggerimenti e selettori; animazioni riducibili;
  contrasto del testo almeno 4,5:1 (WCAG AA) in ogni tema, nomi e descrizioni per i lettori di schermo
- Eseguibile portatile, senza installazione; preferenze in `%APPDATA%\Mapper`, oppure accanto all'exe per l'uso da chiavetta

La ricerca usa l'ultima mappatura. Premi F5 per aggiornare dopo modifiche fatte da altri programmi.
Le cartelle che non si possono leggere vengono saltate ed elencate: clic su **Non leggibili: N** nella barra di stato.
I percorsi oltre 260 caratteri sono supportati. I collegamenti simbolici e le junction NTFS sono mostrati come
collegamenti e non vengono mai seguiti, nemmeno copiando o duplicando (vengono ricreati come collegamenti).
La finestra non si può chiudere mentre è in corso una copia, uno spostamento o un'eliminazione.

## Scorciatoie da tastiera

| Scorciatoia | Azione |
| --- | --- |
| Ctrl+O | Scegli una cartella |
| Ctrl+L | Modifica il percorso |
| F5 | Aggiorna la mappa |
| Ctrl+F | Cerca |
| Ctrl+E | Esporta mappa (formato, anteprima, copia, salva) |
| Ctrl+S | Salva la mappa con nome… |
| Esc | Annulla mappatura/esportazione, azzera la ricerca |
| ↑ ↓ ← → | Spostati, espandi e comprimi nell'albero |
| Invio | Apri un file, espandi una cartella (in ricerca: mostrala nell'albero) |
| F2 | Rinomina |
| Ctrl+C / Ctrl+X / Ctrl+V | Copia, taglia, incolla |
| Canc | Sposta nel Cestino (dopo conferma) |
| Menu / Maiusc+F10 | Azioni sull'elemento selezionato |

## Riga di comando

`mapper-cli.exe` (pubblicato accanto a `Mapper.exe`, oppure `python src/mapper_cli.py` dal sorgente) usa lo stesso
motore senza aprire finestre:

```powershell
mapper-cli scan D:\Lavoro\Progetto --skip-technical | ConvertFrom-Json
mapper-cli snapshot D:\Lavoro\Progetto -o prima.json --hashes
mapper-cli diff prima.json D:\Lavoro\Progetto -f md -o modifiche.md   # codice di uscita 1 = differenze trovate
```

Tutti i comandi, le opzioni e i codici di uscita: [docs/cli.md](docs/cli.md) (in inglese).

## Test e build

```powershell
python -m unittest discover -s tests -v
python tests/smoke_ui.py
pip install pyinstaller
build/build.bat
```

Le build di rilascio usano le dipendenze esatte e controllate con hash di `build/requirements-build.txt`
ed eseguono prima `ruff` (analisi statica, `ruff.toml`) e `pip-audit`; per creare lo stesso ambiente
in locale vedi [docs/security.md](docs/security.md#maintenance) (in inglese).

I test unitari coprono il core di scansione (righe dell'albero identiche alla 1.5, metadati, avanzamento,
annullamento, radici di unità, percorsi lunghi, cartelle negate, junction, copia sicura) e, sul backend,
gli aggiornamenti incrementali dell'albero, la ricerca e *Mostra nell'albero*, l'esportazione, le azioni
sui file (Cestino, nomi univoci per le copie, rinomina delle sole maiuscole, protezione dalla sovrascrittura),
la validazione, le preferenze, le cartelle recenti e la completezza delle traduzioni. Lo smoke test della UI
carica il QML reale, apre ogni finestra e menu, cambia tema, cerca, filtra, esporta, verifica la
virtualizzazione della lista e salva anteprime chiara/scura/compatta in `build/`.

`build/mapper.spec` è l'unica definizione di build, usata sia da `build.bat` sia da GitHub Actions.
Include solo i moduli Qt usati da Mapper (QtQuick, Controls con lo stile Basic, Dialogs, Effects,
Layouts) ed esclude WebEngine, 3D, Charts, Multimedia, PDF, gli altri stili di Controls e i plugin di
debug QML (da 171 MB a circa 32 MB). La build si ferma se una DLL esclusa serve ancora a un file
incluso. UPX resta disattivato e vengono incorporate le informazioni di versione di Windows.

Risultato della build: `portable/Mapper.exe`. Per verificare l'avvio dell'eseguibile:

```powershell
portable/Mapper.exe --smoke-test
```

La build per Windows usa esplicitamente la libreria ICU di sistema richiesta da Qt.
Così si evita un `icuuc.dll` in conflitto incluso in alcuni runtime Python.

## Rilasci

Le versioni seguono `MAJOR.MINOR.PATCH`: PATCH per le correzioni, MINOR per una nuova funzione, MAJOR dopo dieci funzioni.
La versione si trova solo in `VERSION` in `src/mapper_core/version.py`; ogni modifica è elencata in [CHANGELOG.md](CHANGELOG.md).

1. Mentre lavori, descrivi ogni modifica sotto `## [Unreleased]` in `CHANGELOG.md`.
2. Su `main` aggiornato e senza modifiche in sospeso, prepara il rilascio (esempio per una nuova funzione):

   ```powershell
   .venv\Scripts\python build/release.py minor
   ```

   Usa `patch`, `minor`, `major` o una versione precisa come `1.6.0`; aggiungi `--dry-run` per un'anteprima.
   Lo script aggiorna `VERSION`, i titoli dei README e `portable/README.txt`, trasforma `[Unreleased]`
   nella nuova versione con la data di oggi, esegue i test, poi crea il commit di rilascio e il tag
   `vX.Y.Z` sul tuo computer. Non fa mai push.
3. Ricompila l'exe portatile con `build/build.bat` e verificalo con `portable/Mapper.exe --smoke-test`.
4. Pubblica con i comandi stampati dallo script:

   ```powershell
   git push origin main
   git push origin v1.6.0
   ```

   Il tag avvia GitHub Actions. L'esecuzione si ferma se il tag non coincide con `VERSION`; altrimenti
   installa le dipendenze bloccate, esegue analisi statica, controllo delle vulnerabilità e test, compila
   e prova entrambi gli exe e pubblica la release: `Mapper.exe` e `mapper-cli.exe` con i loro codici
   SHA-256, l'SBOM (`Mapper-sbom.cdx.json`), le attestazioni di provenienza e la sezione del CHANGELOG
   di quella versione come testo.

Dopo il push di `main` e prima del push del tag, **Actions → Build and Sign → Run workflow** esegue gli
stessi controlli e la stessa build senza pubblicare nulla, e mostra un'anteprima del testo della release nel riepilogo.

## Sicurezza e privacy

Mapper funziona offline: nessun accesso alla rete, telemetria o invio di errori. Preferenze e cartelle
recenti restano in `%APPDATA%\Mapper`. Le azioni sui file sono limitate alla cartella mappata, non seguono
mai junction o collegamenti simbolici, non sovrascrivono e cancellano solo nel Cestino. Ogni protezione,
i suoi test, cosa viene salvato e come vengono create le release: [docs/security.md](docs/security.md)
(in inglese). Per segnalare una vulnerabilità: [SECURITY.md](SECURITY.md).

## Documentazione

| Documento | Contenuto |
| --- | --- |
| [docs/cli.md](docs/cli.md) | Riga di comando: comandi, opzioni, codici di uscita, esempi PowerShell |
| [docs/formats.md](docs/formats.md) | Formati di esportazione, schemi JSON, file di snapshot e confronto, regole di esclusione |
| [docs/architecture.md](docs/architecture.md) | Moduli, thread, modello dei dati, test |
| [docs/benchmarks.md](docs/benchmarks.md) | Come misurare, risultati 1.5 → 2.0 |
| [docs/security.md](docs/security.md) | Protezioni, privacy, catena di fornitura, verifica di un download |
| [CHANGELOG.md](CHANGELOG.md) | Modifiche di ogni versione |

I documenti in `docs/` sono in inglese.

## Roadmap

- Firma del codice (Authenticode), così SmartScreen riconosce l'editore
- Suddivisione del file dell'interfaccia `Main.qml` in componenti più piccoli
- Prove con i lettori di schermo (Assistente vocale, NVDA)
- Forse un'integrazione locale in sola lettura per gli assistenti di programmazione (MCP), disattivata di default

## Struttura

```text
src/mapper.py       Avvio dell'applicazione Qt e del QML
src/backend.py      Adattatore Qt: modello della lista, lavori in background, azioni sui file e preferenze
src/mapper_core/    Core senza Qt: scansione, albero, esclusioni, esportazioni, snapshot, confronto, copia sicura
src/mapper_cli.py   Riga di comando (mapper-cli.exe), stesso core, senza Qt
src/qml/Main.qml    Interfaccia, componenti condivisi, temi e animazioni
src/Languages/      Cinque dizionari di traduzione (stesse chiavi)
docs/screenshots/   Immagini del README (build/make_screenshots.py)
tests/              Test unitari, smoke test del QML reale, scanner 1.5 congelato come riferimento
benchmarks/         Benchmark riproducibile (alberi sintetici, tempi del motore e dell'app)
build/              Script di build e di rilascio, dipendenze bloccate, icona e manifest di Windows
docs/               Riga di comando, formati, architettura, benchmark, sicurezza
CHANGELOG.md        Modifiche di ogni versione (testo delle release su GitHub)
portable/           Eseguibile per Windows e note d'uso
```

## Licenza

Codice di Mapper: [MIT](LICENSE), Mattia De Lillo.
Font Inter inclusi: SIL Open Font License 1.1, © The Inter Project Authors ([src/fonts/OFL.txt](src/fonts/OFL.txt)).
PySide6/Qt hanno licenze proprie; consulta [Qt licensing](https://doc.qt.io/qt-6/licensing.html)
se ridistribuisci il runtime incluso. Gli eseguibili non vengono mai inseriti nel repository: i push di un tag (`v*`)
eseguono test, build e smoke test dell'exe su GitHub Actions, allegano un'attestazione di provenienza
e il codice SHA-256 e li pubblicano come release. La firma digitale (SignPath) è predisposta ma disattivata.
Un avvio manuale (**Actions → Build and Sign → Run workflow**) esegue solo test, build e avvio di prova
dell'exe, poi lo scarta: non viene caricato né pubblicato nulla.

Per verificare una release scaricata: `gh attestation verify Mapper.exe --repo SoulFlaZ3R/mapper`.
