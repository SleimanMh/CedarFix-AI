from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "shared")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-m", "integration", "tests/integration"],
        cwd=ROOT,
        env=env,
        check=False,
    )
    if result.returncode == 5:
        print("[integration] no integration tests collected")
        return 0
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
