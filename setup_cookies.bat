@echo off
set OUTPUT_DIR=%LOCALAPPDATA%\perplexity-deep-research
set OUTPUT_FILE=%OUTPUT_DIR%\cookies_raw.json
set LOG_FILE=%OUTPUT_DIR%\setup.log

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

if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

echo Closing Chrome to read cookies...
taskkill /F /IM chrome.exe >nul 2>&1
timeout /t 3 /nobreak >nul

echo Extracting cookies...
C:\Python314\python.exe -c "import rookiepy, json; from pathlib import Path; cookies=rookiepy.chrome(domains=['perplexity.ai']); d={c['name']:c['value'] for c in cookies}; Path(r'%OUTPUT_FILE%').write_text(json.dumps(d)); print(f'Extracted {len(d)} cookies')" 2>&1

if %errorlevel% neq 0 (
    echo FAILED - check Chrome is installed and you're logged into perplexity.ai
    pause
    exit /b 1
)

echo Reopening Chrome...
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --restore-last-session

echo.
echo SUCCESS! Cookies saved to %OUTPUT_FILE%
echo The MCP server will use these automatically.
echo Re-run this when cookies expire (every 24 hours).
pause
