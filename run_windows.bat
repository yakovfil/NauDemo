@echo off
setlocal EnableExtensions
set "CONFIGURATION=Debug"
if not "%~1"=="" set "CONFIGURATION=%~1"
set "SCENE=battlezone"
if not "%~2"=="" set "SCENE=%~2"
set "DECLARATION=%~dp0portable_rendering_project.json"
if /I "%SCENE%"=="original" set "DECLARATION=%~dp0portable_original_project.json"
if /I not "%SCENE%"=="battlezone" if /I not "%SCENE%"=="original" (
    echo Usage: %~nx0 [Debug^|Release] [battlezone^|original]
    exit /b 2
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1" -Platform Windows -Configuration "%CONFIGURATION%" -Declaration "%DECLARATION%" -Run
exit /b %ERRORLEVEL%
