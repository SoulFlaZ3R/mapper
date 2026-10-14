# -*- mode: python ; coding: utf-8 -*-
# Spec unico per build.bat e GitHub Actions / Single spec for build.bat and GitHub Actions
# Uso / Usage (dalla cartella build / from the build folder):
#   pyinstaller mapper.spec --distpath ..\portable --workpath .\temp
import os
import re
import sys
from pathlib import Path
from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                 VarFileInfo, VarStruct, VSVersionInfo)

ROOT = Path(SPECPATH).resolve().parent
SRC = ROOT / 'src'
VERSION = re.search(r"^VERSION = '([\d.]+)'", (SRC / 'mapper_core' / 'version.py').read_text(encoding='utf-8'), re.M).group(1)
NUMBERS = tuple(int(n) for n in VERSION.split('.')) + (0,)

# Moduli Qt che Mapper non usa: PyInstaller li includerebbe tutti (WebEngine da solo ~195 MB).
# Qt modules Mapper never uses: PyInstaller would bundle all of them (WebEngine alone ~195 MB).
# Stile Basic (QT_QUICK_CONTROLS_STYLE in mapper.py): gli altri stili e Qt.labs non servono.
# Basic style (QT_QUICK_CONTROLS_STYLE in mapper.py): other styles and Qt.labs are not needed.
UNUSED_QT = re.compile(r'''(?ix)
    webengine | webchannel | websockets | webview | pdf
  | qt3d | qt63d | quick3d | /scene[23]d/ | qt6charts | /qtcharts | graphs | datavisualization
  | location | positioning | multimedia | spatialaudio | texttospeech | sensors
  | qt5compat | core5compat | virtualkeyboard | scxml | statemachine | remoteobjects
  | qt6test | /qttest | quicktest | lottie | wayland | designer | sql | serialport | bluetooth | nfc
  | quicktimeline | /timeline/ | quickparticles | /particles/ | quickshapes | /shapes/ | vectorimage | effectmaker
  | opengl32sw | /translations/ | /qtopengl | qt6openglwidgets | qt6widgets | /qtwidgets | quickwidgets
  | shadertools | qt6labs | /qt/labs/ | designsupport | localstorage | xmllistmodel | qmlnetwork | /qml/qtnetwork/
  | /qtquick/tooling/ | /qmltooling/ | /generic/ | /networkinformation/ | /tls/ | libssl | qdirect2d
  | /imageformats/q(gif|icns|jpeg|tga|tiff|wbmp|webp)
  | quickcontrols2(material|universal|imagine|fluentwinui3|windows|fusion|native) | quicknativestyle | /nativestyle/
  | /controls/(material|universal|imagine|fluentwinui3|windows|macos|ios|fusion|native)/
''')


def keep(entry):
    return not UNUSED_QT.search('/' + entry[0].replace('\\', '/'))


def check_dependencies(kept, dropped):
    """Blocca la build se un file incluso importa una DLL esclusa da UNUSED_QT.
    Stops the build if a bundled file imports a DLL excluded by UNUSED_QT."""
    from PyInstaller.depend.bindepend import get_imports
    kept_names = {os.path.basename(name).lower() for name, _, _ in kept}
    dropped_names = {os.path.basename(name).lower() for name, _, _ in dropped} - kept_names
    broken = sorted(f'{name} -> {dll}' for name, src, _ in kept if src.lower().endswith(('.dll', '.pyd'))
                    for dll, _ in get_imports(src) if dll.lower() in dropped_names)
    if broken:
        raise SystemExit('UNUSED_QT excludes DLLs still required:\n  ' + '\n  '.join(broken))


binaries = []
icu = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'icuuc.dll'
if icu.exists():
    # ICU di sistema: evita un icuuc.dll in conflitto da alcuni runtime Python
    # System ICU: avoids a conflicting icuuc.dll shipped by some Python runtimes
    binaries.append((str(icu), '.'))

a = Analysis(
    [str(SRC / 'mapper.py')],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=[(str(SRC / 'Languages'), 'Languages'), (str(SRC / 'fonts'), 'fonts'),
           (str(SRC / 'qml'), 'qml'), (str(ROOT / 'build' / 'icon.ico'), '.')],
    hiddenimports=[],
    excludes=['tkinter', 'unittest', 'pydoc', 'PySide6.QtWidgets', 'PySide6.QtOpenGL',
              'PySide6.QtOpenGLWidgets', 'PySide6.QtQuickControls2'],
    noarchive=False,
    optimize=1,
)
binaries_kept = [entry for entry in a.binaries if keep(entry)]
check_dependencies(binaries_kept, [entry for entry in a.binaries if not keep(entry)])
a.binaries = binaries_kept
a.datas = [entry for entry in a.datas if keep(entry)]
pyz = PYZ(a.pure)

def version_info(description, filename):
    """Informazioni di versione di Windows / Windows version information."""
    return VSVersionInfo(
        ffi=FixedFileInfo(filevers=NUMBERS, prodvers=NUMBERS),
        kids=[
            StringFileInfo([StringTable('040904B0', [
                StringStruct('CompanyName', 'Mattia De Lillo'),
                StringStruct('FileDescription', description),
                StringStruct('FileVersion', VERSION),
                StringStruct('InternalName', filename.rsplit('.', 1)[0]),
                StringStruct('LegalCopyright', '© 2026 Mattia De Lillo. MIT License.'),
                StringStruct('OriginalFilename', filename),
                StringStruct('ProductName', 'Mapper'),
                StringStruct('ProductVersion', VERSION),
            ])]),
            VarFileInfo([VarStruct('Translation', [0x0409, 1200])]),
        ],
    )


exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Mapper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX disattivato: gli eseguibili compressi vengono segnalati più spesso dagli antivirus
    # UPX off: packed executables are flagged far more often by antivirus heuristics
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    icon=[str(ROOT / 'build' / 'icon.ico')],
    manifest=str(ROOT / 'build' / 'app.manifest'),
    version=version_info('Mapper - folder map and file search', 'Mapper.exe'),
)

# ── mapper-cli.exe: riga di comando, senza Qt / command line, no Qt ──────────
cli = Analysis(
    [str(SRC / 'mapper_cli.py')],
    pathex=[str(SRC)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    excludes=['tkinter', 'unittest', 'pydoc', 'PySide6', 'shiboken6'],
    noarchive=False,
    optimize=1,
)
cli_pyz = PYZ(cli.pure)
cli_exe = EXE(
    cli_pyz,
    cli.scripts,
    cli.binaries,
    cli.datas,
    [],
    name='mapper-cli',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,
    icon=[str(ROOT / 'build' / 'icon.ico')],
    manifest=str(ROOT / 'build' / 'app.manifest'),
    version=version_info('Mapper command line - map, export, snapshot and compare folders', 'mapper-cli.exe'),
)
