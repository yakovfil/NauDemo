@echo off
setlocal EnableExtensions

set "CONFIG=Debug"
if not "%~1"=="" (
    if /I "%~1"=="Debug" (
        set "CONFIG=Debug"
    ) else if /I "%~1"=="Release" (
        set "CONFIG=Release"
    ) else (
        echo Usage: %~nx0 [Debug^|Release]
        exit /b 2
    )
)

set "DEMO_DIR=%~dp0"
set "ENGINE_DIR=%DEMO_DIR%..\NauEngineLite"

if not exist "%ENGINE_DIR%\CMakeLists.txt" (
    echo NauEngineLite was not found beside NauDemo.
    exit /b 1
)

if not defined EMSDK (
    if not exist "%USERPROFILE%\emsdk\emsdk_env.bat" (
        echo Activate Emscripten SDK 6.0.9 or install it at %%USERPROFILE%%\emsdk.
        exit /b 1
    )
    call "%USERPROFILE%\emsdk\emsdk_env.bat"
    if errorlevel 1 exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%DEMO_DIR%web\build.ps1" -Configuration %CONFIG%
if errorlevel 1 exit /b 1

set "PACKAGE=%ENGINE_DIR%\build\web-demo-%CONFIG%\package"
if not exist "%PACKAGE%\serve.py" (
    echo Web package was not produced: "%PACKAGE%"
    exit /b 1
)

pushd "%PACKAGE%" || exit /b 1
echo Serving NauDemo %CONFIG% on http://127.0.0.1:8000/
echo Press Ctrl+C to stop the server; answer Y if CMD asks to terminate the batch job.
python serve.py --port 8000 --open-browser
set "RESULT=%ERRORLEVEL%"
popd
exit /b %RESULT%
