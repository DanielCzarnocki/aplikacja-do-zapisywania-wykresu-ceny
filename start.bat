@echo off
echo Starting CryptoZap Application...
echo =================================
cd /d "%~dp0"
call .\venv\Scripts\activate.bat
echo Virtual environment activated. Starting the server...
echo.
echo You can access the application at: "http://<TWOJ_IP_TAILSCALE>:8000"
echo "(Zastap <TWOJ_IP_TAILSCALE> adresem IP swojego komputera w aplikacji Tailscale)"
echo.
echo Wait a moment for the server to load, then open the link in your browser.
echo Press CTRL+C to stop the application.
echo =================================
uvicorn backend.main:app --host 0.0.0.0 --port 8000
pause
