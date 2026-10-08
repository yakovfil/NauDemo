@echo off
setlocal EnableExtensions
set "CONFIGURATION=Debug"
if not "%~1"=="" set "CONFIGURATION=%~1"
if /I not "%CONFIGURATION%"=="Debug" if /I not "%CONFIGURATION%"=="Release" (
    echo Usage: %~nx0 [Debug^|Release]
    exit /b 2
)
if not defined EMSDK set "EMSDK=%USERPROFILE%\emsdk"
if not exist "%EMSDK%\emsdk_env.bat" (
        echo Activate Emscripten SDK 6.0.9 before running this command.
        exit /b 1
)
call "%EMSDK%\emsdk_env.bat"
if errorlevel 1 exit /b 1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0web\build.ps1" -Configuration "%CONFIGURATION%" -Declaration "%~dp0portable_rendering_project.json" -Serve
exit /b %ERRORLEVEL%
