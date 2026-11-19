@echo off
rem AgentGuard one-click launcher (double-click friendly wrapper for start.ps1).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
echo.
pause
