@echo off
rem 中文：优先使用项目虚拟环境，不存在时回退到 PATH 中的 Python。
rem English: Prefer the project virtual environment and fall back to Python on PATH.
set "PROJECT_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PROJECT_PYTHON%" set "PROJECT_PYTHON=python"
"%PROJECT_PYTHON%" "%~dp0scripts\bootstrap_dev.py" %*
