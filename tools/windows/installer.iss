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
WizardSizePercent=130,125
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
// ---------------------------------------------------------------------------------------------------------------------------------------
// Live details: the setup shows every folder it creates and every file it puts in place (with its size), the shortcuts it makes, and the
// entry in Windows' Apps list; the uninstaller shows every file and folder it deletes. Everything is also written to the setup log (/LOG=...).
// Nothing is downloaded: all files are inside this setup.
// ---------------------------------------------------------------------------------------------------------------------------------------
var
  Details: TNewListBox;
  KnownDirs: TStringList;
  KnownFiles: TStringList;
  LastFile: String;
  DoneFiles: Integer;
  DoneBytes: Int64;
  UDetails: TNewListBox;
  UFiles, UFolders: Integer;
  UBytes: Int64;
  UTotal: Integer;

function FormatSize(Bytes: Int64): String;
begin
  if Bytes >= 1048576 then
    Result := Format('%.1f MB', [Bytes / 1048576.0])
  else if Bytes >= 1024 then
    Result := Format('%.1f KB', [Bytes / 1024.0])
  else
    Result := IntToStr(Bytes) + ' B';
end;

function FindSize(const FR: TFindRec): Int64;
begin
  Result := (Int64(FR.SizeHigh) * 4294967296) + Int64(FR.SizeLow);
end;

// the path as shown in the list: relative to the install folder (the first line says where that is), or %APPDATA% / %LOCALAPPDATA% for the person's data
function Short(const P: String): String;
var
  Root: String;
begin
  Result := P;
  Root := ExpandConstant('{app}') + '\';
  if CompareText(Copy(P, 1, Length(Root)), Root) = 0 then
    Result := Copy(P, Length(Root) + 1, Length(P))
  else if CompareText(Copy(P, 1, Length(ExpandConstant('{userappdata}'))), ExpandConstant('{userappdata}')) = 0 then
    Result := '%APPDATA%' + Copy(P, Length(ExpandConstant('{userappdata}')) + 1, Length(P))
  else if CompareText(Copy(P, 1, Length(ExpandConstant('{localappdata}'))), ExpandConstant('{localappdata}')) = 0 then
    Result := '%LOCALAPPDATA%' + Copy(P, Length(ExpandConstant('{localappdata}')) + 1, Length(P));
end;

function SizeCol(Bytes: Int64): String;
begin
  Result := FormatSize(Bytes);
  while Length(Result) < 9 do Result := ' ' + Result;      // (so the sizes line up as far as the font allows)
end;

procedure Detail(const S: String);
begin
  Log(S);
  if Details <> nil then
  begin
    Details.Items.Add(S);
    Details.ItemIndex := Details.Items.Count - 1;
  end;
end;

// the files and folders (and their size) below a folder
procedure Measure(const Dir: String; var Files, Folders: Integer; var Bytes: Int64);
var
  FR: TFindRec;
begin
  if FindFirst(Dir + '\*', FR) then
  begin
    try
      repeat
        if (FR.Name <> '.') and (FR.Name <> '..') then
        begin
          if (FR.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then
          begin
            Folders := Folders + 1;
            Measure(Dir + '\' + FR.Name, Files, Folders, Bytes);
          end
          else
          begin
            Files := Files + 1;
            Bytes := Bytes + FindSize(FR);
          end;
        end;
      until not FindNext(FR);
    finally
      FindClose(FR);
    end;
  end;
end;

// Setup writes each file under a temporary name (is-XXXX.tmp) and renames it when it is complete; those, and the uninstaller's data file, are not shown.
function Hidden(const Name: String): Boolean;
begin
  Result := ((CompareText(Copy(Name, 1, 3), 'is-') = 0) and (CompareText(ExtractFileExt(Name), '.tmp') = 0)) or (CompareText(Name, 'unins000.dat') = 0);
end;

// Shows every folder and file that has appeared below Dir since the last look, with its size. The file being written right now is left for the next look
// (its size is not final yet); the last look (Final) shows everything that is left.
procedure ScanNew(const Dir: String; Final: Boolean);
var
  FR: TFindRec;
  P: String;
  Size: Int64;
begin
  if FindFirst(Dir + '\*', FR) then
  begin
    try
      repeat
        if (FR.Name <> '.') and (FR.Name <> '..') then
        begin
          P := Dir + '\' + FR.Name;
          if (FR.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then
          begin
            if KnownDirs.IndexOf(P) < 0 then
            begin
              KnownDirs.Add(P);
              Detail('Folder created: ' + Short(P));
            end;
            ScanNew(P, Final);
          end
          else if (not Hidden(FR.Name)) and (KnownFiles.IndexOf(P) < 0) then
          begin
            if Final or (CompareText(P, LastFile) <> 0) then
            begin
              KnownFiles.Add(P);
              Size := FindSize(FR);
              DoneFiles := DoneFiles + 1;
              DoneBytes := DoneBytes + Size;
              Detail('   File   ' + SizeCol(Size) + '   ' + Short(P));
            end;
          end;
        end;
      until not FindNext(FR);
    finally
      FindClose(FR);
    end;
  end;
end;

procedure LookForNew(Final: Boolean);
var
  Root: String;
begin
  Root := ExpandConstant('{app}');
  if DirExists(Root) and (KnownDirs.IndexOf(Root) < 0) then
  begin
    KnownDirs.Add(Root);
    Detail('Folder created: ' + Root + '   (everything below is shown relative to it)');
  end;
  if DirExists(Root) then ScanNew(Root, Final);
end;

procedure InitializeWizard;
begin
  KnownDirs := TStringList.Create;
  KnownDirs.Sorted := True;
  KnownDirs.CaseSensitive := False;
  KnownFiles := TStringList.Create;
  KnownFiles.Sorted := True;
  KnownFiles.CaseSensitive := False;
  Details := TNewListBox.Create(WizardForm);
  Details.Parent := WizardForm.InstallingPage;
  Details.Left := 0;
  Details.Top := WizardForm.FilenameLabel.Top + WizardForm.FilenameLabel.Height;
  if WizardForm.ProgressGauge.Top + WizardForm.ProgressGauge.Height > Details.Top then
    Details.Top := WizardForm.ProgressGauge.Top + WizardForm.ProgressGauge.Height;      // below the progress bar, which must stay visible
  Details.Top := Details.Top + ScaleY(10);
  Details.Width := WizardForm.InstallingPage.Width;
  Details.Height := WizardForm.InstallingPage.Height - Details.Top;
  Details.Anchors := [akLeft, akTop, akRight, akBottom];
end;

procedure CurInstallProgressChanged(CurProgress, MaxProgress: Integer);
var
  Cur: String;
begin
  Cur := WizardForm.FilenameLabel.Caption;
  if (Cur = '') or (Cur = LastFile) then Exit;
  LastFile := Cur;                          // (the file in this label is being written now; the ones before it are complete)
  LookForNew(False);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Files, Folders: Integer;
  Bytes: Int64;
begin
  if CurStep = ssInstall then
    Detail('Installing Roblox Manager {#AppVersion} to ' + ExpandConstant('{app}'))
  else if CurStep = ssPostInstall then
  begin
    LastFile := '';
    LookForNew(True);
    Files := 0; Folders := 0; Bytes := 0;
    Measure(ExpandConstant('{app}'), Files, Folders, Bytes);
    Detail('Done: ' + IntToStr(Files) + ' files in ' + IntToStr(Folders) + ' folders, ' + FormatSize(Bytes) + ' in total');
    if WizardIsTaskSelected('startmenu') then
      Detail('Start menu entry created: ' + ExpandConstant('{autoprograms}\Roblox Manager.lnk'))
    else
      Detail('No Start menu entry (switched off)');
    if WizardIsTaskSelected('desktopicon') then
      Detail('Desktop icon created: ' + ExpandConstant('{autodesktop}\Roblox Manager.lnk'))
    else
      Detail('No desktop icon (switched off)');
    Detail('Registered in Settings > Apps, uninstaller: ' + ExpandConstant('{app}\unins000.exe'));
    WizardForm.FinishedLabel.Caption := WizardForm.FinishedLabel.Caption + #13#10#13#10 + 'Installed to ' + ExpandConstant('{app}') + #13#10 +
      IntToStr(Files) + ' files in ' + IntToStr(Folders) + ' folders, ' + FormatSize(Bytes) + '.';
  end;
end;

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

// ---- uninstall: delete in view, file by file
procedure UDetail(const S: String);
begin
  Log(S);
  if UDetails <> nil then
  begin
    UDetails.Items.Add(S);
    UDetails.ItemIndex := UDetails.Items.Count - 1;
  end;
end;

procedure InitializeUninstallProgressForm;
begin
  UninstallProgressForm.ClientHeight := UninstallProgressForm.ClientHeight + ScaleY(210);
  UDetails := TNewListBox.Create(UninstallProgressForm);
  UDetails.Parent := UninstallProgressForm.InstallingPage;
  UDetails.Left := 0;
  UDetails.Top := UninstallProgressForm.ProgressBar.Top + UninstallProgressForm.ProgressBar.Height + ScaleY(16);
  UDetails.Width := UninstallProgressForm.InstallingPage.Width;
  UDetails.Height := UninstallProgressForm.InstallingPage.Height - UDetails.Top;
  UDetails.Anchors := [akLeft, akTop, akRight, akBottom];
end;

// deletes everything below Dir (and Dir itself unless KeepRoot), telling what is deleted; the uninstaller's own files stay for Inno to remove
procedure RemoveTree(const Dir: String; KeepRoot: Boolean);
var
  FR: TFindRec;
  P: String;
  Size: Int64;
begin
  if FindFirst(Dir + '\*', FR) then
  begin
    try
      repeat
        if (FR.Name <> '.') and (FR.Name <> '..') then
        begin
          P := Dir + '\' + FR.Name;
          if (FR.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then
            RemoveTree(P, False)
          else if (CompareText(P, ExpandConstant('{uninstallexe}')) <> 0) and (CompareText(FR.Name, 'unins000.dat') <> 0) then
          begin
            Size := FindSize(FR);
            if DeleteFile(P) then
            begin
              UFiles := UFiles + 1;
              UBytes := UBytes + Size;
              UDetail('   Deleted   ' + SizeCol(Size) + '   ' + Short(P));
            end
            else
              UDetail('   Could not delete   ' + Short(P));
            if UTotal > 0 then
              UninstallProgressForm.ProgressBar.Position := UninstallProgressForm.ProgressBar.Max * UFiles div UTotal;
          end;
        end;
      until not FindNext(FR);
    finally
      FindClose(FR);
    end;
  end;
  if (not KeepRoot) and RemoveDir(Dir) then
  begin
    UFolders := UFolders + 1;
    UDetail('Folder deleted: ' + Short(Dir));
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  RemoveData: Boolean;
  F, D: Integer;
  B: Int64;
begin
  if CurUninstallStep = usUninstall then
  begin
    // 1. does the person's own data (settings, saved accounts which are encrypted for this Windows user, logs) go too?
    if UninstallSilent then
      RemoveData := CompareText(ExpandConstant('{param:REMOVEDATA|no}'), 'yes') = 0
    else
      RemoveData := MsgBox('Also delete your Roblox Manager settings, saved accounts and logs?' + #13#10#13#10 +
                           'Choose No to keep them for a later reinstall.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES;
    // 2. delete in view
    F := 0; D := 0; B := 0;
    Measure(ExpandConstant('{app}'), F, D, B);
    if RemoveData then
    begin
      Measure(ExpandConstant('{userappdata}\RobloxManager'), F, D, B);
      Measure(ExpandConstant('{localappdata}\RobloxManager'), F, D, B);
    end;
    UTotal := F;
    UFiles := 0; UFolders := 0; UBytes := 0;
    UDetail('Removing Roblox Manager from ' + ExpandConstant('{app}') + ' (' + IntToStr(F) + ' files, ' + FormatSize(B) + ')');
    UDetail('(paths below are relative to the install folder)');
    RemoveTree(ExpandConstant('{app}'), True);
    if RemoveData then
    begin
      UDetail('Removing your settings, saved accounts and logs');
      RemoveTree(ExpandConstant('{userappdata}\RobloxManager'), False);
      RemoveTree(ExpandConstant('{localappdata}\RobloxManager'), False);
    end
    else
      UDetail('Your settings and saved accounts were kept in ' + ExpandConstant('{userappdata}\RobloxManager'));
    UDetail('Shortcuts and the entry in Settings > Apps are removed with the uninstaller');
    UDetail('Done: ' + IntToStr(UFiles) + ' files and ' + IntToStr(UFolders) + ' folders deleted, ' + FormatSize(UBytes) + ' freed');
    if not UninstallSilent then
      MsgBox('Roblox Manager was removed.' + #13#10#13#10 + IntToStr(UFiles) + ' files and ' + IntToStr(UFolders) + ' folders deleted, ' +
             FormatSize(UBytes) + ' freed.', mbInformation, MB_OK);
  end;
end;
