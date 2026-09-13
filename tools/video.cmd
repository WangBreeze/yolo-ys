@echo off
setlocal
set "PYTHONUTF8=1"
if not exist "%~dp0..\.venv\Scripts\python.exe" (
    echo Run python tools\setup-project.py --profile video first.
    exit /b 1
)
"%~dp0..\.venv\Scripts\python.exe" "%~dp0video.py" %*
exit /b %errorlevel%
