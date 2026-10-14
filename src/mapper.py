"""Mapper — Qt Quick desktop launcher / avvio dell'interfaccia Qt Quick."""
import os
import sys
from pathlib import Path
from PySide6.QtCore import QCoreApplication, QLibraryInfo, QTimer, QUrl
from PySide6.QtGui import QFontDatabase, QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from backend import VERSION, MapperBackend


def bundled_only(paths, bundled):
    """
    Percorsi di moduli QML ammessi: solo risorse interne e la cartella inclusa nel pacchetto.
    Qt mette per prima la cartella dell'eseguibile (es. Download): un modulo QML lasciato lì verrebbe caricato.
    Allowed QML import paths: only internal resources and the bundled folder.
    Qt puts the executable's folder first (e.g. Downloads): a QML module dropped there would be loaded.
    """
    def key(path):
        return os.path.normcase(os.path.normpath(path))
    return [p for p in paths if p.startswith('qrc:') or key(p) == key(bundled)]


def exe_folder_excluded(app, engine):
    """Vero se Qt non cerca plugin né moduli QML nella cartella dell'eseguibile / True if Qt never searches the exe's folder."""
    def key(path):
        return os.path.normcase(os.path.normpath(path))
    return key(app.applicationDirPath()) not in {key(p) for p in app.libraryPaths() + engine.importPathList()}


def create_app():
    # Stile Basic via variabile d'ambiente: niente QtWidgets/QtQuickControls2 nel pacchetto
    # Basic style via environment: keeps QtWidgets/QtQuickControls2 out of the bundle
    os.environ['QT_QUICK_CONTROLS_STYLE'] = 'Basic'
    # Plugin Qt solo dal pacchetto, mai dalla cartella dell'exe (es. una DLL lasciata in Download).
    # Il plugin di piattaforma si carica mentre l'app nasce: gli si passa la cartella come argomento
    # (non come variabile d'ambiente, che passerebbe ai programmi aperti da Mapper); gli altri dopo.
    # Qt plugins only from the bundle, never from the exe's folder (e.g. a DLL dropped in Downloads).
    # The platform plugin loads while the app is created: its folder is an argument (not an environment
    # variable, which programs opened from Mapper would inherit); the others are fixed right after.
    plugins = QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath)
    app = QGuiApplication.instance() or QGuiApplication(
        [*sys.argv, '-platformpluginpath', os.path.join(plugins, 'platforms')])
    QCoreApplication.setLibraryPaths([plugins])
    app.setApplicationName('Mapper')
    app.setOrganizationName('Mapper')
    app.setApplicationVersion(VERSION)
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    for font in (base / 'fonts').glob('*.ttf'):
        QFontDatabase.addApplicationFont(str(font))
    families = QFontDatabase.families()
    # Icone di sistema: Fluent (Win 11) o MDL2 (Win 10) hanno gli stessi codepoint
    # System icons: Fluent (Win 11) and MDL2 (Win 10) share the same codepoints
    icon_font = next((f for f in ('Segoe Fluent Icons', 'Segoe MDL2 Assets') if f in families), '')
    icon = base / 'icon.ico' if getattr(sys, 'frozen', False) else base.parent / 'build' / 'icon.ico'
    app.setWindowIcon(QIcon(str(icon)))
    backend = MapperBackend()
    engine = QQmlApplicationEngine()
    engine.setImportPathList(bundled_only(engine.importPathList(), QLibraryInfo.path(QLibraryInfo.LibraryPath.QmlImportsPath)))
    diagnostics = []
    def report(errors):
        diagnostics.extend(error.toString() for error in errors)
        if sys.stderr:
            for error in errors:
                print(error.toString(), file=sys.stderr)
    engine.warnings.connect(report)
    context = engine.rootContext()
    context.setContextProperty('backend', backend)
    context.setContextProperty('fileModel', backend.model)
    context.setContextProperty('diffModel', backend.diff_model)
    context.setContextProperty('uiFont', 'Inter' if 'Inter' in families else 'Segoe UI')
    context.setContextProperty('iconFont', icon_font)
    engine.load(QUrl.fromLocalFile(str(base / 'qml' / 'Main.qml')))
    if not engine.rootObjects():
        raise RuntimeError('Unable to load the Mapper QML interface\n' + '\n'.join(diagnostics))
    app.aboutToQuit.connect(backend.shutdown)
    return app, engine, backend


if __name__ == '__main__':
    import ctypes
    if sys.platform == 'win32':
        # ID stabile tra versioni: le icone fissate sulla barra restano valide
        # Stable across versions so pinned taskbar icons keep working
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('mattiadl.mapper')
    try:
        app, engine, backend = create_app()
    except Exception:
        import traceback
        import tempfile
        # Il nome utente nei percorsi non finisce nel log / The user name in paths stays out of the log
        from backend import data_dir, redact_home
        details = redact_home(traceback.format_exc())
        # Log in %APPDATA%/Mapper (exe) o in build/ (sorgente) / Log in %APPDATA%/Mapper (exe) or build/ (source)
        log_dir = data_dir() if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent / 'build'
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            (log_dir / 'mapper-startup.log').write_text(details, encoding='utf-8')
        except OSError:
            (Path(tempfile.gettempdir()) / 'mapper-startup.log').write_text(details, encoding='utf-8')
        # In smoke test esce con errore senza finestre modali (CI) / Smoke test exits non-zero without modal windows (CI)
        if '--smoke-test' in sys.argv:
            sys.exit(1)
        if sys.platform == 'win32':
            ctypes.windll.user32.MessageBoxW(None, details, 'Mapper', 0x10)
        raise
    if '--smoke-test' in sys.argv:
        if not exe_folder_excluded(app, engine):
            print('Qt plugins or QML modules may load from the executable folder', file=sys.stderr)
            backend.shutdown()
            sys.exit(1)
        QTimer.singleShot(1500, app.quit)
    exit_code = app.exec()
    backend.shutdown()
    # Destroy QML bindings while their context objects are still alive.
    del engine
    sys.exit(exit_code)
