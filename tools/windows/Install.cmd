@echo off
setlocal
title Install Roblox Manager
set "SRC=%~dp0"
set "DEST=%LOCALAPPDATA%\Programs\RobloxManager"
echo.
echo Roblox Manager will be installed for your user in:
echo   %DEST%
echo (no administrator rights needed). Your settings are kept if it was installed before.
echo.
if exist "%DEST%\python\pythonw.exe" (
    taskkill /f /im pythonw.exe /fi "WINDOWTITLE eq Roblox Manager*" >nul 2>&1
)
if exist "%DEST%" rmdir /s /q "%DEST%" >nul 2>&1
xcopy "%SRC%*" "%DEST%\" /E /I /Y /Q >nul
if errorlevel 1 (
    echo.
    echo Copying failed. Close Roblox Manager if it is open and try again.
    pause
    exit /b 1
)
set "DESK="
choice /c YN /m "Also put a shortcut on the desktop"
if errorlevel 2 (set "DESK=") else (set "DESK=-Desktop")
powershell -NoProfile -ExecutionPolicy Bypass -File "%DEST%\shortcut.ps1" -Dest "%DEST%" %DESK%
echo.
echo Installed. Find "Roblox Manager" in the Start menu.
choice /c YN /m "Start it now"
if errorlevel 2 exit /b 0
start "" "%DEST%\python\pythonw.exe" "%DEST%\app\launcher.py"
exit /b 0
