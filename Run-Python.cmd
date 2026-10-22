@echo off
setlocal
cd /d "%~dp0"
if defined LOCALDESK_PYTHON (
  "%LOCALDESK_PYTHON%" %*
  exit /b
)
if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" %*
  exit /b
)
py -3 -c "import sys; assert sys.version_info >= (3,11)" >nul 2>nul
if not errorlevel 1 (
  py -3 %*
  exit /b
)
if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
  "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" %*
  exit /b
)
python -c "import sys; assert sys.version_info >= (3,11)" >nul 2>nul
if not errorlevel 1 (
  python %*
  exit /b
)
echo Python 3.11 or newer was not found. Install Python from python.org, then try again.
echo You can also set LOCALDESK_PYTHON to the full path of a Python executable.
exit /b 1
