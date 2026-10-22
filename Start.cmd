@echo off
call "%~dp0Run-Python.cmd" "%~dp0app.py" %*
if errorlevel 1 pause
