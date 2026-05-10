@echo off
setlocal

set OUTPUT_DIR=%LOCALAPPDATA%\perplexity-deep-research
set OUTPUT_FILE=%OUTPUT_DIR%\cookies_raw.json

echo ============================================
echo  Perplexity Deep Research - Cookie Setup
echo ============================================

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Not running as Administrator.
    echo Right-click this file and select "Run as administrator"
    pause
    exit /b 1
)

REM Find a usable python interpreter (prefer py launcher, fall back to PATH)
set PYTHON_EXE=
where py >nul 2>&1 && set PYTHON_EXE=py -3
if "%PYTHON_EXE%"=="" (
    where python >nul 2>&1 && set PYTHON_EXE=python
)
if "%PYTHON_EXE%"=="" (
    echo ERROR: Python not found on PATH. Install Python 3.12+ and re-run.
    pause
    exit /b 1
)

if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

echo Closing Chrome to read cookies...
taskkill /F /IM chrome.exe >nul 2>&1
timeout /t 3 /nobreak >nul

echo Extracting cookies via %PYTHON_EXE%...
%PYTHON_EXE% -c "import rookiepy, json; from pathlib import Path; cookies=rookiepy.chrome(domains=['perplexity.ai']); d={c['name']:c['value'] for c in cookies}; Path(r'%OUTPUT_FILE%').write_text(json.dumps(d)); print(f'Extracted {len(d)} cookies')"

if %errorlevel% neq 0 (
    echo FAILED - check Chrome is installed, you're logged into perplexity.ai, and rookiepy is installed (pip install rookiepy)
    pause
    exit /b 1
)

echo Reopening Chrome...
if exist "%PROGRAMFILES%\Google\Chrome\Application\chrome.exe" (
    start "" "%PROGRAMFILES%\Google\Chrome\Application\chrome.exe" --restore-last-session
) else if exist "%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe" (
    start "" "%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe" --restore-last-session
) else if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" (
    start "" "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" --restore-last-session
)

echo.
echo SUCCESS! Cookies saved to %OUTPUT_FILE%
echo The MCP server will use these automatically.
echo Re-run this when cookies expire (every 24 hours).
pause
endlocal
