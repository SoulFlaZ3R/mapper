"""Mapper — Qt Quick desktop launcher / avvio dell'interfaccia Qt Quick."""
import os
import sys
from pathlib import Path
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QFontDatabase, QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from backend import VERSION, MapperBackend


def create_app():
    # Stile Basic via variabile d'ambiente: niente QtWidgets/QtQuickControls2 nel pacchetto
    # Basic style via environment: keeps QtWidgets/QtQuickControls2 out of the bundle
    os.environ['QT_QUICK_CONTROLS_STYLE'] = 'Basic'
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
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
        details = traceback.format_exc()
        log_dir = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent / 'build'
        try:
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
        QTimer.singleShot(1500, app.quit)
    exit_code = app.exec()
    backend.shutdown()
    # Destroy QML bindings while their context objects are still alive.
    del engine
    sys.exit(exit_code)
