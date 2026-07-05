@echo off
setlocal
cd /d "%~dp0"

echo =======================================================
echo Starting SWEWS (Space Weather Early Warning System)
echo =======================================================

echo.
echo [1/2] Starting FastAPI Backend Server in a new window...
start "SWEWS API Backend" cmd /k "venv\Scripts\python.exe -m src.api.app"

echo.
echo [2/2] Starting Vite Frontend Server...
pnpm --filter @workspace/swews dev

endlocal
