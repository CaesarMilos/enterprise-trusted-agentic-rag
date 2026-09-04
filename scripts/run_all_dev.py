"""中文：在本地开发环境中统一启动 API、Worker 和 UI。

English: Start API, worker, and UI together for local development.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path


def main() -> None:
    """中文：监督三个子进程，任一退出时终止其余进程。

    English: Supervise three child processes and terminate the others when one exits.
    """

    project_root = Path(__file__).resolve().parents[1]
    commands = (
        (sys.executable, str(project_root / "scripts" / "run_api.py")),
        (sys.executable, str(project_root / "scripts" / "run_worker.py")),
        (sys.executable, str(project_root / "scripts" / "run_ui.py")),
    )
    processes = [subprocess.Popen(command, cwd=project_root) for command in commands]
    try:
        while all(process.poll() is None for process in processes):
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10.0)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()
