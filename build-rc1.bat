@echo off
setlocal

cd /d "%~dp0"
set "TWANO_BUILD_PYTHON=%~dp0.venv\Scripts\python.exe"

if not exist "%TWANO_BUILD_PYTHON%" (
    echo Twano's private Python environment is missing.
    echo Run launcher.bat once, close Twano, then run this file again.
    pause
    exit /b 1
)

echo Checking RC1 build tools...
"%TWANO_BUILD_PYTHON%" -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo Installing the pinned RC1 build tools...
    "%TWANO_BUILD_PYTHON%" -m pip install --disable-pip-version-check -r requirements-build.txt
    if errorlevel 1 goto :tool_failed
)

echo Building the timestamped RC1 Windows package...
powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_windows_app.ps1
if errorlevel 1 goto :build_failed

echo.
echo RC1 build completed. Open C:\Twano\Builds to find the newest
echo timestamped Twano-R4-RC1-Windows folder.
echo If Inno Setup is not installed, the portable ZIP is still produced but
echo the Setup.exe installer is skipped.
pause
exit /b 0

:tool_failed
echo.
echo The build tools could not be installed. Check the internet connection,
echo then run build-rc1.bat again.
pause
exit /b 1

:build_failed
echo.
echo The RC1 build did not complete. Read the message above, correct it, then
echo run build-rc1.bat again. Existing timestamped builds are not overwritten.
pause
exit /b 1
