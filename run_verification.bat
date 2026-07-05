@echo off
setlocal

cd /d "%~dp0"

set "MODE=%~1"
if "%MODE%"=="" set "MODE=quick"

if /I not "%MODE%"=="quick" if /I not "%MODE%"=="full" (
  echo Usage: run_verification.bat [quick^|full]
  exit /b 1
)

echo Running SWEWS verification in %MODE% mode...
python scripts\verify_system.py --mode %MODE%

if errorlevel 1 (
  echo Verification failed.
  exit /b %errorlevel%
)

echo.
echo Report saved to outputs\verification\verification_report.json
endlocal
