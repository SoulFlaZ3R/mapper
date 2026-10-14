MAPPER 2.0 — PySide6 + Qt Quick/QML
© 2026 Mattia De Lillo

ITALIANO

Apri Mapper.exe. Non serve installare Python.
Scegli una cartella: Sfoglia, trascinala sulla finestra, incolla il percorso
o scegline una tra le recenti. La mappatura parte da sola.
Espandi le cartelle con la freccia, con un doppio clic o con le frecce ← →.
Cerca: scrivi nel campo di ricerca; i risultati mostrano dove si trova ogni file.
Doppio clic su una cartella trovata (o "Mostra nell'albero") la apre nell'albero.
Clicca un tipo di file nel grafico o nella legenda per filtrare; di nuovo per togliere il filtro.
Clic destro o ⋯ per le azioni: apri, mostra in Esplora risorse, copia percorso,
taglia/copia/incolla, duplica, nuovo file/cartella, rinomina, elimina.
Elimina sposta nel Cestino. Le copie non sovrascrivono mai: "nome - copia".
Esporta mappa: anteprima, copia negli appunti o salva come testo, Markdown, JSON o CSV.
Aprire un programma o uno script (.exe, .bat, .ps1 …) chiede prima conferma.
Usa F5 per aggiornare dopo modifiche fatte fuori da Mapper.
Le cartelle non leggibili vengono elencate (clic su "Non leggibili" nella barra di stato).
Collegamenti simbolici e junction sono mostrati come collegamenti e mai seguiti.
Impostazioni: 5 temi, 5 lingue, riduzione animazioni (anteprima dal vivo).
Preferenze e cartelle recenti sono salvate in %APPDATA%\Mapper (nessun file accanto all'exe).
Per l'uso da chiavetta: crea un config.json vuoto accanto a Mapper.exe.

Riga di comando: mapper-cli.exe (stesso motore, senza finestra). Esempio in PowerShell:
  mapper-cli snapshot C:\Cartella -o prima.json
  mapper-cli diff prima.json C:\Cartella -f md -o modifiche.md
Guida completa: https://github.com/SoulFlaZ3R/mapper/blob/main/docs/cli.md

ENGLISH

Open Mapper.exe. Python installation is not required.
Choose a folder: Browse, drag it onto the window, paste its path
or pick a recent one. Mapping starts automatically.
Expand folders with the arrow, a double click or the ← → keys.
Search: type in the search field; results show where each file is.
Double-click a found folder (or "Show in tree") to open it in the tree.
Click a file type in the chart or legend to filter; click again to clear.
Right-click or ⋯ for actions: open, show in Explorer, copy path,
cut/copy/paste, duplicate, new file/folder, rename, delete.
Delete moves items to the Recycle Bin. Copies never overwrite: "name - copy".
Export map: preview, copy to the clipboard or save as text, Markdown, JSON or CSV.
Opening a program or script (.exe, .bat, .ps1 …) asks for confirmation first.
Press F5 to refresh changes made outside Mapper.
Folders that cannot be read are listed (click "Not readable" in the status bar).
Symbolic links and junctions are shown as links and never followed.
Settings: 5 themes, 5 languages and reduced motion (live preview).
Preferences and recent folders are saved in %APPDATA%\Mapper (no file next to the exe).
For USB use: create an empty config.json next to Mapper.exe.

Command line: mapper-cli.exe (same engine, no window). PowerShell example:
  mapper-cli snapshot C:\Folder -o before.json
  mapper-cli diff before.json C:\Folder -f md -o changes.md
Full guide: https://github.com/SoulFlaZ3R/mapper/blob/main/docs/cli.md

SHORTCUTS / SCORCIATOIE
Ctrl+O: browse / sfoglia
Ctrl+L: edit path / modifica percorso
F5: refresh / aggiorna
Ctrl+F: search / cerca
Ctrl+E: export map / esporta mappa
Ctrl+S: save map as / salva mappa con nome
Escape: cancel, clear search / annulla, azzera ricerca
Arrows / Frecce: move, expand, collapse / muovi, espandi, comprimi
Enter: open / apri
F2: rename / rinomina
Ctrl+C / Ctrl+X / Ctrl+V: copy, cut, paste / copia, taglia, incolla
Delete / Canc: Recycle Bin / Cestino
Menu, Shift+F10: actions / azioni

Source: https://github.com/SoulFlaZ3R/mapper
