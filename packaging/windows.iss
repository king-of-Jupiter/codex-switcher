; Inno Setup script: Windows installer for Codex Switcher.
; Version is injected by CI: ISCC /DAppVersion=x.y.z

#ifndef AppVersion
#define AppVersion "0.0.0"
#endif

[Setup]
AppId={{7C1E4A9F-52B3-4D6E-8F07-A90B3C5D21E8}}
AppName=Codex Switcher
AppVersion={#AppVersion}
AppPublisher=codex-switcher
DefaultDirName={autopf}\Codex Switcher
DefaultGroupName=Codex Switcher
UninstallDisplayName=Codex Switcher
UninstallDisplayIcon={app}\CodexSwitcher.exe
OutputDir=..\release
OutputBaseFilename=CodexSwitcher-{#AppVersion}-setup-x64
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
SetupIconFile=..\assets\icon.ico
PrivilegesRequiredOverridesAllowed=dialog commandline
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\CodexSwitcher.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Codex Switcher"; Filename: "{app}\CodexSwitcher.exe"
Name: "{group}\Uninstall Codex Switcher"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Codex Switcher"; Filename: "{app}\CodexSwitcher.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\CodexSwitcher.exe"; Description: "{cm:LaunchProgram,Codex Switcher}"; Flags: nowait postinstall skipifsilent
