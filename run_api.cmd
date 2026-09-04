@echo off
rem 中文：启动本地 API，并避免 CMD 环境变量末尾空格。
rem English: Start the local API without trailing-space environment-variable hazards.
set "PROJECT_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PROJECT_PYTHON%" set "PROJECT_PYTHON=python"
"%PROJECT_PYTHON%" "%~dp0scripts\run_api.py" %*
