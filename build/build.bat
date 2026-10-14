@echo off
REM ============================================================================
REM  Mapper - Build script per .exe portable
REM  Mapper - Build script for portable .exe
REM ============================================================================
REM
REM  Prerequisiti / Prerequisites:
REM    pip install -r ..\requirements.txt pyinstaller
REM
REM  Uso / Usage:
REM    build\build.bat   (dalla root del progetto / from project root)
REM    build.bat         (dalla cartella build/ / from build/ folder)
REM
REM  Output:
REM    portable\Mapper.exe
REM
REM  Nota sulla firma digitale / Digital signature note:
REM    Senza firma, Windows SmartScreen potrebbe mostrare un avviso alla prima
REM    esecuzione. Per firmare l'exe, usare signtool.exe:
REM
REM    Without signing, Windows SmartScreen may show a warning on first run.
REM    To sign the exe, use signtool.exe:
REM
REM      signtool sign /f certificato.pfx /p %%CERT_PASSWORD%% /t https://timestamp.digicert.com ..\portable\Mapper.exe
REM
REM ============================================================================

REM Imposta directory corrente alla cartella build/
cd /d "%~dp0"

echo [BUILD] Avvio build Mapper / Starting Mapper build...

REM Tutte le opzioni sono in mapper.spec / All options live in mapper.spec
pyinstaller --noconfirm --clean mapper.spec --distpath ..\portable --workpath .\temp

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Build fallita / Build failed!
    pause
    exit /b 1
)

echo.
echo [BUILD] Build completata! / Build complete!
echo [BUILD] Output: ..\portable\Mapper.exe  +  ..\portable\mapper-cli.exe
echo.
pause
