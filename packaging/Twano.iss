#ifndef SourceRoot
  #error SourceRoot must point to the PyInstaller Twano folder.
#endif
#ifndef OutputRoot
  #define OutputRoot "."
#endif
#define ProductName "Twano's eBook Manager"
#define ExecutableName "Twano eBook Manager.exe"

[Setup]
AppId={{3B6AB8EA-E7D8-4CC5-9470-4D10FBA699C8}
AppName={#ProductName}
AppVersion=R4 RC1
AppPublisher=Twano
DefaultDirName={localappdata}\Programs\{#ProductName}
DefaultGroupName={#ProductName}
OutputDir={#OutputRoot}
OutputBaseFilename=Twano's eBook Manager Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
UninstallDisplayName={#ProductName}
UninstallDisplayIcon={app}\{#ExecutableName}
SetupIconFile=..\design\branding\twano-book-logo.ico
SetupLogging=yes

[Files]
Source: "{#SourceRoot}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#ProductName}"; Filename: "{app}\{#ExecutableName}"
Name: "{autodesktop}\{#ProductName}"; Filename: "{app}\{#ExecutableName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Run]
Filename: "{app}\{#ExecutableName}"; Description: "Launch {#ProductName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; User catalogue, settings, backups, covers and quarantine are deliberately
; stored outside {app} and are never removed by the normal uninstaller.
