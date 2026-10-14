"""
Genera gli screenshot del README su una cartella dimostrativa (nessun dato personale).
Builds the README screenshots from a demo folder (no personal data).

Uso / Usage:  python build/make_screenshots.py [--root "D:\\Acme Studio"] [--out docs/screenshots]
La cartella demo viene creata e, alla fine, rimossa solo se creata dallo script.
The demo folder is created and, at the end, removed only if the script created it.
"""
import argparse
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from PySide6 import QtQuick  # noqa: F401  tipi QQuickWindow/QQuickItem / QQuickWindow/QQuickItem types
from PySide6.QtCore import QMetaObject, QObject
from mapper import create_app

DEMO = {
    'Brand': ['logo.svg', 'logo-dark.svg', 'palette.pdf', 'brand-guidelines.pdf', 'typography.pdf'],
    'Clients/Northwind': ['proposal.docx', 'invoice-2026-03.pdf', 'invoice-2026-04.pdf', 'kickoff-notes.md'],
    'Clients/Contoso': ['contract.pdf', 'scope.docx', 'timeline.xlsx'],
    'Clients/Fabrikam': ['brief.pdf', 'moodboard.png', 'feedback-round-1.md'],
    'Design/Mockups': ['home.png', 'dashboard.png', 'settings.png', 'mobile-home.png', 'mobile-search.png'],
    'Design/Icons': ['search.svg', 'folder.svg', 'export.svg', 'settings.svg'],
    'Docs': ['README.md', 'roadmap.md', 'meeting-notes.txt', 'onboarding.md', 'report-q1.pdf', 'report-q2.pdf'],
    'Photos/2026-03 Offsite': ['IMG_0412.jpg', 'IMG_0413.jpg', 'IMG_0418.jpg', 'IMG_0421.jpg', 'IMG_0427.jpg'],
    'Code/app': ['main.py', 'scanner.py', 'settings.json', 'requirements.txt'],
    'Code/app/tests': ['test_scanner.py', 'test_ui.py'],
    '': ['budget-2026.xlsx', 'contacts.csv', 'todo.md'],
}


def build_demo(root):
    for folder, files in DEMO.items():
        (root / folder).mkdir(parents=True, exist_ok=True)
        for name in files:
            (root / folder / name).write_text('demo', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default=r'D:\Acme Studio')
    parser.add_argument('--out', default=str(ROOT / 'docs' / 'screenshots'))
    args = parser.parse_args()
    root, out = Path(args.root), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    created = not root.exists()
    if not created and any(root.iterdir()):
        sys.exit(f'{root} exists and is not empty: choose another --root')
    build_demo(root)

    app, engine, backend = create_app()
    win = engine.rootObjects()[0]
    tree = win.findChild(QObject, 'fileList')

    def settle(seconds=0.6):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)

    def wait(predicate, timeout=15):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        assert predicate(), backend.state
        settle()

    def shot(name):
        # Nessun tooltip o hover dovuto al cursore reale / No tooltip or hover from the real cursor
        win.findChild(QObject, 'toolTip').setProperty('target', None)
        settle(0.2)
        image = win.grabWindow()
        assert image.save(str(out / f'{name}.png')), name
        print('saved', out / f'{name}.png', f'{image.width()}x{image.height()}')

    def popup(name, open_=True):
        item = win.findChild(QObject, name)
        assert QMetaObject.invokeMethod(item, 'open' if open_ else 'close')
        settle()
        return item

    with tempfile.TemporaryDirectory() as config_dir:
        try:
            # Preferenze isolate: niente cartelle recenti reali / Isolated prefs: no real recent folders
            backend.config_path = Path(config_dir) / 'config.json'
            backend._recent = [str(root), str(root / 'Clients'), str(root / 'Design')]
            backend.recentChanged.emit()
            # Finestra lontana dal cursore: niente stati hover casuali / Window away from the cursor: no stray hover
            win.setPosition(-3000, 0)
            win.setWidth(1280)
            win.setHeight(800)

            # 1. Schermata iniziale / Start screen
            backend.previewPreferences('light', 'en', True)
            settle()
            shot('01-start')

            # 2. Albero esplorato / Explored tree
            backend.openFolder(str(root))
            wait(lambda: backend.state['scanned'] and backend.model.rowCount() > 0)
            for folder in ['Clients', 'Clients/Northwind', 'Design', 'Design/Mockups']:
                backend.setExpanded(str(root / folder), True)
                settle(0.3)
            wait(lambda: backend.model.indexOf(str(root / 'Design' / 'Mockups' / 'home.png')) >= 0)
            tree.setProperty('currentIndex', backend.model.indexOf(str(root / 'Clients' / 'Northwind' / 'proposal.docx')))
            settle()
            # Altezza tale che la legenda mostri solo righe intere (34 px + 2 di spazio)
            # Height chosen so the legend shows whole rows only (34 px + 2 spacing)
            legend = win.findChild(QObject, 'legend')
            extra = (34 - int(legend.property('height')) % 36) % 36
            win.setHeight(800 + extra)
            settle()
            shot('02-explorer-light')
            backend.previewPreferences('dark', 'en', True)
            settle()
            shot('03-explorer-dark')

            # 3. Ricerca con evidenziazione / Search with highlighting
            backend.setQuery('report')
            wait(lambda: backend.model.rowCount() == 2)
            tree.setProperty('currentIndex', 0)
            shot('04-search')
            backend.clearFilters()
            wait(lambda: backend.state['query'] == '')

            # 4. Filtro per tipo dal grafico / File type filter from the chart
            backend.setExtension('.pdf')
            wait(lambda: backend.model.rowCount() > 0 and all(backend.model.item(i)['extension'] == '.pdf' for i in range(backend.model.rowCount())))
            shot('05-filter-type')
            backend.clearFilters()
            wait(lambda: backend.state['extension'] == '')

            # 5. Menu contestuale / Context menu
            target = str(root / 'Clients' / 'Northwind' / 'proposal.docx')
            row = backend.model.indexOf(target)
            tree.setProperty('currentIndex', row)
            win.setProperty('targetPath', target)
            menu = win.findChild(QObject, 'contextMenu')
            menu.setProperty('x', 330)
            menu.setProperty('y', 250)
            popup('contextMenu')
            shot('06-context-menu')
            popup('contextMenu', False)

            # 6. Esporta mappa / Export map
            popup('exportDialog')
            shot('07-export')
            popup('exportDialog', False)

            # 7. Impostazioni (tema blu, italiano) / Settings (blue theme, Italian)
            backend.previewPreferences('blue', 'it', True)
            settle()
            popup('settingsDialog')
            shot('08-settings')
            popup('settingsDialog', False)
        finally:
            backend.shutdown()
            win.close()
            app.processEvents()
            del engine
            if created:
                shutil.rmtree(root, ignore_errors=True)


if __name__ == '__main__':
    main()
