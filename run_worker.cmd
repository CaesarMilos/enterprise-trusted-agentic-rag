@echo off
rem 中文：启动持久任务 Worker。
rem English: Start the durable background worker.
set "PROJECT_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PROJECT_PYTHON%" set "PROJECT_PYTHON=python"
"%PROJECT_PYTHON%" "%~dp0scripts\run_worker.py" %*
