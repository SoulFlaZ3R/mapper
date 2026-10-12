"""Exercise the real QML window and render previews; run on Windows.
Set MAPPER_SHOTS=<folder> to also save menu and dialog screenshots there."""
import os
import sys
import tempfile
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from PySide6.QtCore import qInstallMessageHandler, QObject, QMetaObject, QCoreApplication, QEvent
from PySide6 import QtQuick  # noqa: F401  tipi QQuickWindow/QQuickItem in Python / QQuickWindow/QQuickItem Python types
from mapper import create_app

errors = []
def messages(kind, context, text):
    print(text, file=sys.stderr)
    if any(term in text for term in ('Error', 'ReferenceError', 'TypeError', 'Binding loop', 'Unable to assign',
                                     'does not support', 'Cannot read', 'undefined', 'Could not', 'is not an Item')):
        errors.append(text)
qInstallMessageHandler(messages)
app, engine, backend = create_app()
window = engine.rootObjects()[0]
warnings = []
engine.warnings.connect(lambda items: warnings.extend(error.toString() for error in items))
build = Path(__file__).resolve().parents[1] / 'build'
shots = Path(os.environ['MAPPER_SHOTS']) if os.environ.get('MAPPER_SHOTS') else None

def wait(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert predicate(), backend.state
    assert not errors, errors
    assert not warnings, warnings

def settle(seconds=0.4):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)

def shot(name):
    if shots:
        assert window.grabWindow().save(str(shots / (name + '.png')))

def names():
    return [row['itemName'] for row in backend.model.rows]

try:
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder) / 'Workspace'
        (root / 'Design assets').mkdir(parents=True)
        (root / 'Documents').mkdir()
        for name in ['Brand guidelines.pdf', 'Roadmap.md', 'Notes.txt', 'Project.json', 'Cover.png', 'Research.csv']:
            (root / name).touch()
        (root / 'Documents' / 'nested-report.txt').touch()
        backend.config_path = Path(folder) / 'preferences.json'
        backend.previewPreferences('light', 'it', False)
        settle()
        shot('empty-light')
        backend.openFolder(str(root))
        wait(lambda: not backend.state['busy'] and backend.model.rowCount() == 8)
        for theme in ['light', 'dark', 'blue', 'red', 'system']:
            backend.previewPreferences(theme, 'it', False)
            settle(0.2)
        backend.previewPreferences('light', 'it', False)
        window.setWidth(1320); window.setHeight(850)
        settle()
        for name in ['settingsDialog', 'exportDialog', 'editDialog', 'deleteDialog', 'guideDialog']:
            dialog = window.findChild(QObject, name)
            assert dialog is not None, name
            window.setProperty('targetPath', str(root / 'Roadmap.md'))
            assert QMetaObject.invokeMethod(dialog, 'open')
            settle()
            assert dialog.property('visible'), name
            shot(name)
            assert QMetaObject.invokeMethod(dialog, 'close')
            settle()
        menu = window.findChild(QObject, 'contextMenu')
        menu.setProperty('x', 420); menu.setProperty('y', 330)
        assert QMetaObject.invokeMethod(menu, 'open')
        settle()
        assert menu.property('visible')
        shot('contextMenu-light')
        assert QMetaObject.invokeMethod(menu, 'close')
        settle()
        assert window.grabWindow().save(str(build / 'preview-qt-light.png'))
        backend.previewPreferences('dark', 'en', True)
        settle()
        assert QMetaObject.invokeMethod(menu, 'open')
        settle()
        shot('contextMenu-dark')
        assert QMetaObject.invokeMethod(menu, 'close')
        settle()
        assert window.grabWindow().save(str(build / 'preview-qt-dark.png'))
        # Ricerca → mostra nell'albero / Search → show in tree
        backend.setQuery('nested-report')
        wait(lambda: names() == ['nested-report.txt'])
        settle()
        shot('search-dark')
        revealed = []
        backend.revealed.connect(revealed.append)
        backend.reveal(str(root / 'Documents' / 'nested-report.txt'))
        wait(lambda: revealed and backend.state['query'] == '')
        assert window.findChild(QObject, 'fileList').property('currentIndex') == revealed[0]
        assert window.findChild(QObject, 'filterField').property('text') == ''
        backend.setExtension('.png')
        wait(lambda: names() == ['Cover.png'])
        backend.clearFilters()
        backend.expandAll(False)
        window.setWidth(860); window.setHeight(600)
        settle()
        assert window.grabWindow().save(str(build / 'preview-qt-compact.png'))
        backend.exportMap(str(Path(folder) / 'output.txt'))
        wait(lambda: not backend.state['busy'])
        assert (Path(folder) / 'output.txt').exists()
        for i in range(1000):
            (root / ('file-%04d.txt' % i)).touch()
        backend.scan()
        wait(lambda: not backend.state['busy'] and backend.model.rowCount() > 1000)
        settle()
        tree = window.findChild(QObject, 'fileList')
        rows = [item for item in tree.property('contentItem').childItems() if item.objectName() == 'fileRow']
        assert 0 < len(rows) < 100, 'ListView must virtualize delegates: ' + str(len(rows))
        assert not errors and not warnings, errors + warnings
        print('QT_UI_SMOKE_OK: QML, dialogs, menus, themes, resize, search/reveal, filters, export, virtualization, previews')
finally:
    backend.shutdown()
    window.close()
    app.processEvents()
    engine.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert not errors and not warnings, errors + warnings
