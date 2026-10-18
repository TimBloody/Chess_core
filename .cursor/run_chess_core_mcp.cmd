@echo off
setlocal
set ROOT=%~dp0..
cd /d "%ROOT%"
set "PYTHONPATH=%ROOT%\src;%PYTHONPATH%"
set PYTHONUNBUFFERED=1
set PYTHONUTF8=1
if exist "%ROOT%\.venv\Scripts\python.exe" (
  "%ROOT%\.venv\Scripts\python.exe" -m chess_core.tools.mcp_server
) else (
  python -m chess_core.tools.mcp_server
)
