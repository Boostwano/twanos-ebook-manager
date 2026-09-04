# Twano R4 Beta 2 Known Issues and Boundaries

These limits are intentional and should not be mistaken for hidden failures.

- The delivered Beta 2 ZIP is a Python source test package, not a signed
  installer. `launcher.bat` needs internet access the first time it creates the
  private environment and installs dependencies.
- The Windows executable/installer scripts require PyInstaller and optionally
  Inno Setup. PyInstaller could not be downloaded in the restricted build
  environment used for this package, so no untested executable is claimed.
- **Check for Updates** reports the current release/status. It does not silently
  download or install an update. Signed update delivery remains a production
  release gate.
- Open Library lookup requires internet access, is user-triggered, and is
  intended for low-volume interactive use. A provider outage leaves the local
  catalogue usable.
- The external approved plugin catalogue is intentionally empty in Beta 2.
  Approved built-in providers can be installed now; arbitrary third-party
  packages are refused.
- Calibre integration detects, validates, opens, and can route a library folder
  into Twano's normal scan preview. Twano never writes directly to Calibre's
  `metadata.db`.
- Duplicate quarantine is limited to confirmed identical file contents.
  Possible editions can be reviewed or marked intentional but are never
  automatically removed.
- Twano catalogues ebooks and opens them in another reader; it does not include
  a built-in EPUB/PDF reader.
- Full statistical analytics were intentionally omitted to keep the application
  approachable. Library Health contains actionable quality information.
- Accessibility, high-DPI, large-library performance, mapped-drive, UNC/NAS,
  Calibre-version, installer, and upgrade matrices still require real-computer
  Beta testing before production sign-off.
