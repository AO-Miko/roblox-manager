@echo off
setlocal
title Uninstall Roblox Manager
set "DEST=%LOCALAPPDATA%\Programs\RobloxManager"
echo.
echo This removes Roblox Manager from %DEST% and its shortcuts.
choice /c YN /m "Continue"
if errorlevel 2 exit /b 0
powershell -NoProfile -ExecutionPolicy Bypass -File "%DEST%\shortcut.ps1" -Remove
echo.
echo Your settings, saved accounts (encrypted for your Windows user) and logs are in:
echo   %APPDATA%\RobloxManager
echo   %LOCALAPPDATA%\RobloxManager
choice /c YN /m "Delete them too"
if errorlevel 2 (set "WIPE=") else (set "WIPE=1")
if defined WIPE (
    rmdir /s /q "%APPDATA%\RobloxManager" >nul 2>&1
    rmdir /s /q "%LOCALAPPDATA%\RobloxManager" >nul 2>&1
)
rem this file lives in the folder that is being deleted, so the deleting is done by a separate process after a moment
start "" /b cmd /c "ping -n 3 127.0.0.1 >nul & rmdir /s /q ""%DEST%"""
echo Done.
exit /b 0
