@echo off
setlocal

cd /d "%~dp0"
set "TWANO_PYTHON=%~dp0.venv\Scripts\python.exe"
set "TWANO_APP=%~dp0src\app.py"
set "TWANO_REQUIREMENTS=%~dp0requirements.txt"
set "TWANO_REQUIREMENTS_MARKER=%~dp0.venv\twano-requirements.txt"
set "TWANO_BOOTSTRAP=C:\Users\Boostwano\AppData\Local\Programs\Python\Python312\python.exe"

if not exist "%TWANO_BOOTSTRAP%" set "TWANO_BOOTSTRAP=python"
if not exist "%TWANO_PYTHON%" goto :create_environment
goto :check_requirements

:create_environment
echo First run: creating Twano's private Python environment...
"%TWANO_BOOTSTRAP%" -m venv "%~dp0.venv"
if errorlevel 1 goto :setup_failed

:check_requirements
if not exist "%TWANO_REQUIREMENTS_MARKER%" goto :install_requirements
fc /b "%TWANO_REQUIREMENTS%" "%TWANO_REQUIREMENTS_MARKER%" >nul
if errorlevel 1 goto :install_requirements
goto :launch

:install_requirements
echo Installing or updating Twano's required packages...
"%TWANO_PYTHON%" -m pip install --disable-pip-version-check -r "%TWANO_REQUIREMENTS%"
if errorlevel 1 goto :setup_failed
copy /y "%TWANO_REQUIREMENTS%" "%TWANO_REQUIREMENTS_MARKER%" >nul
if errorlevel 1 goto :setup_failed
echo Twano setup completed successfully.

:launch
echo Starting Twano...
"%TWANO_PYTHON%" "%TWANO_APP%"

if errorlevel 1 (
    echo.
    echo Twano closed because of an error.
    pause
    exit /b 1
)

endlocal
exit /b 0

:setup_failed
echo.
echo Twano setup could not finish. Check the message above, then run
echo launcher.bat again. Internet access is needed on the first run.
pause
exit /b 1

