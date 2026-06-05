import signal
import subprocess
import sys
from typing import List


processes: List[subprocess.Popen] = []
shutting_down = False


def _terminate_all() -> None:
    global shutting_down
    shutting_down = True
    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()


def _handle_signal(signum, _frame) -> None:
    print(f"[runner] received signal {signum}; stopping child services", flush=True)
    _terminate_all()
    sys.exit(128 + signum)


def _start(spec: str) -> subprocess.Popen:
    try:
        name, target = spec.split("=", 1)
        module_app, port = target.rsplit(":", 1)
    except ValueError as exc:
        raise SystemExit(
            "Service spec must be name=module.path:app:port, "
            f"got: {spec!r}"
        ) from exc

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        module_app,
        "--host",
        "0.0.0.0",
        "--port",
        port,
    ]
    print(f"[runner] starting {name}: {' '.join(cmd)}", flush=True)
    return subprocess.Popen(cmd)


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: run_group.py name=module.path:app:port [...]")

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    for spec in sys.argv[1:]:
        processes.append(_start(spec))

    import time

    while True:
        for process in processes:
            code = process.poll()
            if code is not None:
                if not shutting_down:
                    print(
                        f"[runner] child pid={process.pid} exited with code {code}; stopping group",
                        flush=True,
                    )
                    _terminate_all()
                return code or 0

        time.sleep(1)


if __name__ == "__main__":
    raise SystemExit(main())
