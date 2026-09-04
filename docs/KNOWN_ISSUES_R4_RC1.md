# Twano R4 RC1 Known Issues and Release Gates

- Portable acceptance builds intentionally remain source-based and use
  `launcher.bat` while application testing continues. Installer, upgrade and
  uninstall acceptance is deferred until the application is approved for its
  final installable build.
- No production code-signing certificate is configured. Any locally built RC1
  executable or installer is therefore unsigned and Windows may display an
  unknown-publisher warning.
- Live metadata and cover results remain dependent on provider availability,
  rate limits and user-owned credentials where required.
- Amazon may alternate between genuine book results and a bot/access response.
  Twano parses the current genuine result layout, but correctly marks the
  provider unavailable/update-needed when Amazon withholds that layout.
- Google Images currently returns no recognised image-result data in the live
  provider check and is marked **Provider Update Needed**. Other active cover
  providers continue to work, and **Cover File...** remains available.
- Google Books can rate-limit keyless or isolated test profiles. A valid
  user-owned key may be configured in Plugins; automated tests never expose or
  copy that credential.
- Mapped-drive, UNC/NAS, security-software, clean-install, upgrade and uninstall
  checks must be performed on real Windows systems using the exact candidate
  artifacts.
- Update checking reports installed release status only. Automatic signed
  update installation remains disabled until final update metadata and signing
  are approved.
