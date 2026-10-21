; Roblox Manager installer (Inno Setup 6). Built by tools/build_installer.sh:
;   ISCC /DAppVersion=1.4.0 /DPackageDir=<the RobloxManager folder made by tools/build_windows.py> /DOutDir=<where the setup goes> installer.iss
; Installs for the current Windows user only (no administrator rights), by default into %APPDATA%\RobloxManager\App (next to the person's settings, which live
; in %APPDATA%\RobloxManager). The person may choose any folder they can write to: the app updates itself by replacing its own app folder.
; Everything else is optional: the Start menu entry (what Windows search finds), the desktop icon, and starting the app at the end.
#ifndef AppVersion
  #error Give the version: ISCC /DAppVersion=1.2.3
#endif
#ifndef PackageDir
  #error Give the package folder: ISCC /DPackageDir=...
#endif
#ifndef OutDir
  #define OutDir "."
#endif

[Setup]
AppId={{B9F4E6A8-3D2C-4C57-9E3A-5D8A1F7C2E41}
AppName=Roblox Manager
AppVersion={#AppVersion}
AppVerName=Roblox Manager {#AppVersion}
AppPublisher=AO-Miko
AppPublisherURL=https://github.com/AO-Miko/roblox-manager
AppSupportURL=https://github.com/AO-Miko/roblox-manager/issues
AppUpdatesURL=https://github.com/AO-Miko/roblox-manager/releases
VersionInfoVersion={#AppVersion}
VersionInfoDescription=Roblox Manager setup
DefaultDirName={userappdata}\RobloxManager\App
DisableProgramGroupPage=yes
DisableDirPage=no
UsePreviousAppDir=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutDir}
OutputBaseFilename=Roblox-Manager-Setup-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
WizardStyle=modern
SetupIconFile={#PackageDir}\app\icon.ico
UninstallDisplayIcon={app}\app\icon.ico
UninstallDisplayName=Roblox Manager
CloseApplications=yes
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startmenu"; Description: "Add Roblox Manager to the &Start menu (so you can find it by pressing the Windows key and typing its name)"; GroupDescription: "Shortcuts:"
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
; everything of the package except the portable helpers (Install.cmd and friends): the installer replaces them
Source: "{#PackageDir}\*"; DestDir: "{app}"; Excludes: "Install.cmd,Uninstall.cmd,shortcut.ps1,Roblox Manager.cmd,README.txt"; Flags: recursesubdirs createallsubdirs ignoreversion

[InstallDelete]
; a clean app folder: the app may have updated itself since the last install, and old files must not linger
Type: filesandordirs; Name: "{app}\app"
Type: filesandordirs; Name: "{app}\app.previous"
Type: filesandordirs; Name: "{app}\app.replaced"
Type: filesandordirs; Name: "{app}\app.new-*"
Type: files; Name: "{app}\Install.cmd"
Type: files; Name: "{app}\Uninstall.cmd"
Type: files; Name: "{app}\shortcut.ps1"

[Icons]
Name: "{autoprograms}\Roblox Manager"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\app\launcher.py"""; WorkingDir: "{app}"; IconFilename: "{app}\app\icon.ico"; Comment: "Manage your Roblox accounts"; Tasks: startmenu
Name: "{autodesktop}\Roblox Manager"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\app\launcher.py"""; WorkingDir: "{app}"; IconFilename: "{app}\app\icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\app\launcher.py"""; WorkingDir: "{app}"; Description: "Start Roblox Manager"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; the app folder changes when the app updates itself, so the whole install folder is removed
Type: filesandordirs; Name: "{app}"

[Code]
// The app updates itself by replacing its own folder, so it must live in a folder the person can write to (not Program Files or Windows).
function NextButtonClick(CurPageID: Integer): Boolean;
var
  d: String;
begin
  Result := True;
  if CurPageID = wpSelectDir then
  begin
    d := Lowercase(WizardDirValue);
    if (Pos(Lowercase(ExpandConstant('{commonpf64}')), d) = 1) or (Pos(Lowercase(ExpandConstant('{commonpf32}')), d) = 1) or
       (Pos(Lowercase(ExpandConstant('{win}')), d) = 1) then
    begin
      MsgBox('Roblox Manager updates itself, so it has to be installed in a folder you can write to.' + #13#10#13#10 +
             'Please choose another folder (for example one in your user folder, or on another drive).', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

// At uninstall, ask whether the person's own data goes too (settings, saved accounts which are encrypted for this Windows user, logs).
// Silent uninstall keeps it unless /REMOVEDATA=yes is given.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  remove: Boolean;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if UninstallSilent then
      remove := CompareText(ExpandConstant('{param:REMOVEDATA|no}'), 'yes') = 0
    else
      remove := MsgBox('Also delete your Roblox Manager settings, saved accounts and logs?' + #13#10#13#10 +
                       'Choose No to keep them for a later reinstall.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES;
    if remove then
    begin
      DelTree(ExpandConstant('{userappdata}\RobloxManager'), True, True, True);
      DelTree(ExpandConstant('{localappdata}\RobloxManager'), True, True, True);
    end;
  end;
end;
