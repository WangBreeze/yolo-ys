@echo off
setlocal
set "PYTHONUTF8=1"
pushd "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
    echo Run python tools\setup-project.py --profile windows first.
    popd
    exit /b 1
)
".venv\Scripts\python.exe" -m game_agent %*
set "AGENT_RESULT=%errorlevel%"
popd
exit /b %AGENT_RESULT%
