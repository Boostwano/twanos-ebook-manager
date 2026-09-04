# Twano's eBook Manager

Twano R4 RC1 is a Windows desktop application for scanning, browsing,
repairing, and protecting ebook libraries. It is designed for everyday users:
the main navigation stays small, changes are previewed, important operations
create verified backups, and duplicate files are never automatically deleted.

## Start the application

Double-click `launcher.bat`. On the first run it creates Twano's private
Python environment, installs the required packages, confirms setup completed,
and starts the application. Use the same file for every later test.

Beta 1 starts with a fresh catalogue under `%LOCALAPPDATA%\Twano`. Older
development data under `%USERPROFILE%\.twanos_ebook_manager` is preserved.

## What is included

- responsive Home, Library, Scan, Metadata, Health, Plugins, and Settings pages
- grid/list library browsing, search, filters, details, and collections
- multi-folder local, mapped-drive, UNC, and Calibre-library source workflows
- one-click preview of all enabled watched folders and protected Apply All
- verified catalogue backups, Restore, audit history, and supported Undo
- one-button lookup across active metadata plugins, independent cover search,
  protected API-key setup, and field-level approval
- explainable duplicates with exact-copy quarantine and Restore
- deterministic, actionable Library Health
- controlled approved-plugin catalogue and compatibility checks
- accessibility settings, in-app guidance, release notes, and packaging tools

Full analytics and a built-in ebook reader are intentionally omitted.

## Test this release

Beta 2 acceptance is complete. Follow the
[RC1 testing guide](docs/R4-RC1-Testing-Guide.md) for production-candidate
packaging and upgrade checks.
Read [known issues and boundaries](docs/KNOWN_ISSUES_R4_BETA2.md) before using a
real library.

## Development checks

```powershell
.\.venv\Scripts\python.exe -m compileall -q src tests tools
.\.venv\Scripts\python.exe -m pytest -v
```

## Documentation

- [User Guide](docs/USER_GUIDE.md)
- [Release Notes](docs/RELEASE_NOTES_R4_BETA2.md)
- [Security Policy](SECURITY.md)
- [Licence](LICENSE.md)
- [Third-Party Notices](THIRD_PARTY_NOTICES.md)
- [Privacy and Diagnostics](docs/PRIVACY_AND_DIAGNOSTICS.md)
- [Calibre Plugin ZIP Audit](docs/CALIBRE_PLUGIN_ZIP_AUDIT.md)
- [Architecture](ARCHITECTURE.md)
- [Database Notes](docs/database.md)
- [Windows Build Guide](docs/WINDOWS_BUILD_GUIDE.md)
- [Master Delivery Roadmap](docs/Twano-Master-Delivery-Roadmap.md)
