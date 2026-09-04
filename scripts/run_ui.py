"""中文：使用当前 Python 环境启动 Streamlit UI。

English: Start the Streamlit UI with the current Python environment.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    """中文：以绝对脚本路径启动 UI，不依赖当前工作目录或 PYTHONPATH。

    English: Launch from an absolute script path without relying on cwd or PYTHONPATH.
    """

    project_root = Path(__file__).resolve().parents[1]
    subprocess.run(
        (
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(project_root / "src" / "enterprise_rag" / "ui" / "streamlit_app.py"),
            "--server.address",
            "127.0.0.1",
        ),
        check=True,
        cwd=project_root,
    )


if __name__ == "__main__":
    main()
