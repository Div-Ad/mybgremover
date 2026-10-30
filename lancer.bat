@echo off
rem Lance l'app de détourage : http://127.0.0.1:8765
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Premier lancement : installation de l'environnement Python...
  python -m venv .venv || goto erreur
  .venv\Scripts\python -m pip install -q -r requirements.txt || goto erreur
)
rem une version précédente encore ouverte garderait le port : on l'arrête
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { $o = $_.OwningProcess; Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -eq $o -and $_.CommandLine -like '*app.serveur*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force } }"
start "" http://127.0.0.1:8765
.venv\Scripts\python -m uvicorn app.serveur:app --host 127.0.0.1 --port 8765
goto :eof
:erreur
echo L'installation a echoue : Python 3.11 ou plus doit etre installe.
pause
