# Creates (or removes) the Start menu / desktop shortcut of Roblox Manager. Used by Install.cmd and Uninstall.cmd.
param([string]$Dest, [switch]$Desktop, [switch]$Remove)
$menu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Roblox Manager.lnk'
$desk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Roblox Manager.lnk'
if ($Remove) {
    Remove-Item -LiteralPath $menu, $desk -ErrorAction SilentlyContinue
    exit 0
}
function Make($path) {
    $s = (New-Object -ComObject WScript.Shell).CreateShortcut($path)
    $s.TargetPath = Join-Path $Dest 'python\pythonw.exe'
    $s.Arguments = '"' + (Join-Path $Dest 'app\launcher.py') + '"'
    $s.WorkingDirectory = $Dest
    $s.IconLocation = Join-Path $Dest 'app\icon.ico'
    $s.Description = 'Roblox Manager'
    $s.Save()
}
Make $menu
if ($Desktop) { Make $desk }
