@echo off
setlocal enabledelayedexpansion
title Harmony-Healing
mode con cols=81 lines=25
powershell -noprofile -command "& { $w = $Host.UI.RawUI; $b = $w.BufferSize; $b.Height = 6000; $w.BufferSize = $b; }" >nul 2>&1

:: Change to script's directory
cd /d "%~dp0"

:: Check for Administrator privileges
net session >nul 2>&1
if %errorLevel% NEQ 0 (
    echo   ERROR: Administrator rights required for first-time setup
    echo   Please right-click this file and select Run as administrator
    echo.
    timeout /t 4 >nul
    exit /b 1
)


:MENU
cls
echo ================================================================================
echo     Harmonic-Healer : Batch Menu
echo ================================================================================
echo.
echo.
echo.
echo.
echo.
echo.
echo     1. Run Main Program
echo.
echo     2. Run Main Program (debug)
echo.
echo     3. Install Requirements
echo.
echo.
echo.
echo.
echo.
echo ================================================================================
set /p choice="Selection; Menu Option = 1-3, Exit Batch = X: "

if /i "%choice%"=="1" goto RUN_SILENT
if /i "%choice%"=="2" goto RUN_DEBUG
if /i "%choice%"=="3" goto INSTALL
if /i "%choice%"=="X" goto EOF
goto MENU


:RUN_SILENT
:: Launches without any console window. All Python output is suppressed.
:: The batch window counts down then closes — leaving only the GUI.
if exist ".venv\Scripts\pythonw.exe" (
    cls
    echo ================================================================================
    echo     Harmonic-Healer : Launching...
    echo ================================================================================
    echo.
    echo   Starting Harmonic-Healer silently.
    echo   This window will close automatically.
    echo.
    start "" /D "%~dp0" ".venv\Scripts\pythonw.exe" launcher.py
    echo   Closing in 3 seconds...
    timeout /t 3 >nul
    goto EOF
) else (
    echo.
    echo   [ERROR] Virtual Environment not found. Please run Option 3 first.
    echo.
    pause
)
goto MENU


:RUN_DEBUG
:: Launches with the console window visible, showing all Python output.
:: Pauses when the program exits so output can be reviewed.
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    python launcher.py
    pause
) else (
    echo.
    echo   [ERROR] Virtual Environment not found. Please run Option 3 first.
    echo.
    pause
)
goto MENU


:INSTALL
:: Use venv python if available, otherwise system python for bootstrapping
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe installer.py
) else (
    python installer.py
)
pause
goto MENU


:EOF
exit