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
VERSION = re.search(r"^VERSION = '([\d.]+)'", (SRC / 'backend.py').read_text(encoding='utf-8'), re.M).group(1)
NUMBERS = tuple(int(n) for n in VERSION.split('.')) + (0,)

# Moduli Qt che Mapper non usa: PyInstaller li includerebbe tutti (WebEngine da solo ~195 MB).
# Qt modules Mapper never uses: PyInstaller would bundle all of them (WebEngine alone ~195 MB).
UNUSED_QT = re.compile(r'''(?ix)
    webengine | webchannel | websockets | webview | qt6pdf | /qtpdf | pdfquick
  | qt3d | quick3d | qt6charts | /qtcharts | graphs | datavisualization
  | location | positioning | multimedia | spatialaudio | texttospeech | sensors
  | qt5compat | core5compat | virtualkeyboard | scxml | statemachine | remoteobjects
  | qt6test | /qttest | quicktest | lottie | wayland | designer | sql | serialport | bluetooth | nfc
  | quicktimeline | quickparticles | /particles/ | shapes/designhelpers | vectorimage | effectmaker
  | opengl32sw | /translations/ | /qtopengl | qt6widgets | /qtwidgets | quickwidgets
  | /controls/(material|universal|imagine|fluentwinui3|windows|macos|ios)/
''')


def keep(entry):
    return not UNUSED_QT.search('/' + entry[0].replace('\\', '/'))


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
a.binaries = [entry for entry in a.binaries if keep(entry)]
a.datas = [entry for entry in a.datas if keep(entry)]
pyz = PYZ(a.pure)

version = VSVersionInfo(
    ffi=FixedFileInfo(filevers=NUMBERS, prodvers=NUMBERS),
    kids=[
        StringFileInfo([StringTable('040904B0', [
            StringStruct('CompanyName', 'Mattia De Lillo'),
            StringStruct('FileDescription', 'Mapper - folder map and file search'),
            StringStruct('FileVersion', VERSION),
            StringStruct('InternalName', 'Mapper'),
            StringStruct('LegalCopyright', '© 2026 Mattia De Lillo. MIT License.'),
            StringStruct('OriginalFilename', 'Mapper.exe'),
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
    version=version,
)
