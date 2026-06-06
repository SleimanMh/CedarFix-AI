from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GROUPS = [
    ("shared", "tests/shared"),
    ("text_understanding", "tests/text_understanding"),
    ("priority_engine", "tests/priority_engine"),
    ("embedding_service", "tests/embedding_service"),
    ("clustering_service", "tests/clustering_service"),
    ("routing_engine", "tests/routing_engine"),
    ("gateway", "tests/gateway"),
    ("image_understanding", "tests/image_understanding"),
    ("review_service", "tests/review_service"),
    ("monitoring_service", "tests/monitoring_service"),
    ("explanation_service", "tests/explanation_service"),
    ("frontend", "tests/frontend"),
    ("docker", "tests/docker"),
    ("config", "tests/config"),
]


def main() -> int:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "shared")
    failed: list[str] = []

    for name, path in GROUPS:
        print(f"\n[unit] running {name}", flush=True)
        result = subprocess.run(
            [sys.executable, "-m", "pytest", path, "-q"],
            cwd=ROOT,
            env=env,
            check=False,
        )
        if result.returncode != 0:
            failed.append(name)

    if failed:
        print(f"\n[unit] failed groups: {', '.join(failed)}", file=sys.stderr)
        return 1
    print("\n[unit] all groups passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
