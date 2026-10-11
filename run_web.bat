@echo off
setlocal EnableExtensions
set "CONFIGURATION=Debug"
if not "%~1"=="" set "CONFIGURATION=%~1"
if /I not "%CONFIGURATION%"=="Debug" if /I not "%CONFIGURATION%"=="Release" (
    echo Usage: %~nx0 [Debug^|Release] [battlezone^|original]
    exit /b 2
)
if not defined EMSDK set "EMSDK=%USERPROFILE%\emsdk"
if not exist "%EMSDK%\emsdk_env.bat" (
        echo Activate Emscripten SDK 6.0.9 before running this command.
        exit /b 1
)
call "%EMSDK%\emsdk_env.bat"
if errorlevel 1 exit /b 1
set "SCENE=battlezone"
if not "%~2"=="" set "SCENE=%~2"
set "DECLARATION=%~dp0portable_rendering_project.json"
if /I "%SCENE%"=="original" set "DECLARATION=%~dp0portable_original_project.json"
if /I not "%SCENE%"=="battlezone" if /I not "%SCENE%"=="original" (
    echo Usage: %~nx0 [Debug^|Release] [battlezone^|original]
    exit /b 2
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0web\build.ps1" -Configuration "%CONFIGURATION%" -Declaration "%DECLARATION%" -Serve
exit /b %ERRORLEVEL%
