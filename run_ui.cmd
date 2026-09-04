@echo off
rem 中文：在 127.0.0.1 启动 Streamlit UI。
rem English: Start Streamlit UI on 127.0.0.1.
set "PROJECT_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PROJECT_PYTHON%" set "PROJECT_PYTHON=python"
"%PROJECT_PYTHON%" "%~dp0scripts\run_ui.py" %*
