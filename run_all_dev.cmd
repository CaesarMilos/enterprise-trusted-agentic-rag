@echo off
rem 中文：一次启动 API、Worker 和 UI。
rem English: Start API, worker, and UI together.
set "PROJECT_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PROJECT_PYTHON%" set "PROJECT_PYTHON=python"
"%PROJECT_PYTHON%" "%~dp0scripts\run_all_dev.py" %*
