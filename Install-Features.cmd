@echo off
call "%~dp0Run-Python.cmd" -m pip install --target "%~dp0.packages" --upgrade -r "%~dp0requirements.txt"
if errorlevel 1 (
  echo Installation failed. Check your internet connection and Python pip installation.
) else (
  echo Optional Python features installed. Restart LocalDesk.
)
pause
