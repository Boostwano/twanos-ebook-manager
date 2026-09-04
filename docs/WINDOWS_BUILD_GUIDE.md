# Windows Build Guide

## Source test package

From the repository root:

```powershell
$stamp = Get-Date -Format "yyyy-MM-dd-HHmm"
$archive = "C:\Twano\Builds\$stamp-Twano-R4-RC1-Source-Candidate.zip"
.\.venv\Scripts\python.exe tools\build_release_zip.py `
  $archive
```

The timestamp is placed first so Windows sorts builds chronologically. The
builder refuses to overwrite an existing ZIP. If a filename without a leading
timestamp is supplied, the builder adds the current timestamp automatically.

Validate from a clean temporary extraction:

```powershell
.\.venv\Scripts\python.exe tools\validate_release_zip.py `
  $archive `
  --python .\.venv\Scripts\python.exe
```

The validator compiles Python, runs every automated test, performs a seven-page
UI smoke capture, and checks version information.

## Portable Windows application

For the simplest local build, double-click:

```text
build-rc1.bat
```

It checks or installs the pinned build dependency and runs the same
overwrite-safe PowerShell build below. Existing timestamped builds are never
replaced.

For a manual build, install the pinned build dependency:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
```

Then run:

```powershell
powershell -ExecutionPolicy Bypass -File tools\build_windows_app.ps1
```

The script uses PyInstaller's onedir/windowed mode and produces a portable ZIP
inside a new timestamp-first output folder. It refuses to reuse an existing
output folder and creates an adjacent SHA256 file. If Inno Setup is present,
it also compiles `packaging\Twano.iss` and hashes the installer.

For RC1, install the recommended **64-bit Inno Setup 7** release. The build
script detects standard Inno Setup 7 and 6 installation folders automatically.

## Production requirements not satisfied by a local Beta build

- code-sign the executable and installer;
- publish a verified checksum through a trusted release channel;
- test clean install, upgrade, uninstall/reinstall, and rollback;
- run supported Windows and security-software compatibility checks;
- verify that user data under `%LOCALAPPDATA%\Twano` is preserved;
- test the exact signed artefacts rather than a different local build.
