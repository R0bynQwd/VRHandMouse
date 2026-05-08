@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "LOCAL_PYTHON=%ROOT%\PythonRuntime\python.exe"
set "VENV_DIR=%ROOT%\.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "REQ_FILE=%ROOT%\requirements.txt"

echo ==========================================
echo        VR tools launcher monitor
echo ==========================================
echo Director: %ROOT%
echo.

if not exist "%LOCAL_PYTHON%" (
    echo [ERROR] Lipseste runtime-ul local: %LOCAL_PYTHON%
    exit /b 1
)

if not exist "%VENV_PYTHON%" (
    echo [SETUP] Creez .venv local...
    "%LOCAL_PYTHON%" -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [ERROR] Nu am putut crea .venv.
        exit /b 1
    )
) else (
    echo [OK] .venv exista deja.
)

if not exist "%REQ_FILE%" (
    echo [ERROR] Lipseste requirements.txt
    exit /b 1
)

"%VENV_PYTHON%" -c "import importlib.util,sys;mods=('psutil','cv2','mediapipe');missing=[m for m in mods if importlib.util.find_spec(m) is None];print(','.join(missing));sys.exit(1 if missing else 0)"
if errorlevel 1 (
    echo [SETUP] Instalez dependentele din requirements.txt...
    "%VENV_PYTHON%" -m pip install --upgrade pip
    if errorlevel 1 (
        echo [ERROR] Actualizarea pip a esuat.
        exit /b 1
    )
    "%VENV_PYTHON%" -m pip install -r "%REQ_FILE%"
    if errorlevel 1 (
        echo [ERROR] Instalarea dependentelor a esuat.
        exit /b 1
    )
) else (
    echo [OK] Dependentele sunt instalate.
)

echo.
echo [RUN] vision_tracker.py
echo Trackerul ascunde consola implicit si afiseaza statusul in iconita din system tray.
echo Dublu-click pe iconita pentru a afisa consola. Pentru diagnostic vizual foloseste manual: vision_tracker.py --debug-preview
echo Apasa ESC sau Ctrl+C pentru iesire.
"%VENV_PYTHON%" "%ROOT%\vision_tracker.py"
