@echo off
setlocal EnableExtensions
set "CONFIGURATION=Debug"
if not "%~1"=="" set "CONFIGURATION=%~1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1" -Platform Windows -Configuration "%CONFIGURATION%" -Run
exit /b %ERRORLEVEL%
