; Inno Setup script for the Windows installer. Built by CI (windows-latest
; ships ISCC.exe) via:
;   iscc packaging\windows.iss
; Expects dist\windows\NetworkOutageAnalyzer.exe to already exist (built by
; packaging/windows.spec). Per-user install, no admin rights required.

#define MyAppName "Network Outage Analyzer"
#define MyAppExeName "NetworkOutageAnalyzer.exe"
#define MyAppPublisher "Mitchell G. Altherr"

[Setup]
AppName={#MyAppName}
AppVersion=1.0
DefaultDirName={localappdata}\NetworkOutageAnalyzer
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=NetworkOutageAnalyzer-Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "..\dist\windows\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
