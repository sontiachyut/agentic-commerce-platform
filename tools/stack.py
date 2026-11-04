"""Manage only this project's loopback API and synthetic source processes."""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"
STATE = LOCAL / "stack.json"
SERVICES = {
    "source": ("commerce.simulator:create_source_app", 8511, "/health"),
    "api": ("commerce.api:create_app", 8510, "/health/ready"),
}


def health(port, path):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=1) as response:
            return json.loads(response.read())
    except Exception:
        return None


def owns_process(pid, module):
    command = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="], text=True, capture_output=True
    ).stdout
    if f"-m uvicorn {module}" not in command:
        return False
    proc = Path(f"/proc/{pid}/cwd")
    if proc.exists():
        return proc.resolve() == ROOT
    cwd = subprocess.run(
        ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"], text=True, capture_output=True
    ).stdout
    return "n" + str(ROOT) in cwd.splitlines()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["up", "down", "status"])
    parser.add_argument("--provider", choices=["baseline", "codex"], default="baseline")
    args = parser.parse_args()
    LOCAL.mkdir(exist_ok=True, mode=0o700)
    LOCAL.chmod(0o700)
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    if args.command == "status":
        print(
            json.dumps(
                {name: health(port, path) for name, (_, port, path) in SERVICES.items()}, indent=2
            )
        )
        return
    if args.command == "down":
        for name, data in state.items():
            pid = data["pid"]
            if owns_process(pid, SERVICES[name][0]):
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                deadline = time.monotonic() + 10
                while owns_process(pid, SERVICES[name][0]) and time.monotonic() < deadline:
                    time.sleep(0.1)
        STATE.unlink(missing_ok=True)
        print(
            "Stopped this project's API/source. PostgreSQL volume and business data are preserved."
        )
        return
    for name, (module, port, path) in SERVICES.items():
        existing = health(port, path)
        if existing:
            if name == "api" and existing.get("model_provider") != args.provider:
                raise SystemExit(
                    "API already uses another provider. Run stack.py down before changing it."
                )
            continue
        environment = dict(os.environ)
        environment["COMMERCE_MODEL_PROVIDER"] = args.provider
        log_path = LOCAL / f"{name}.log"
        log_path.touch(mode=0o600, exist_ok=True)
        log_path.chmod(0o600)
        with log_path.open("ab") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    module,
                    "--factory",
                    "--no-access-log",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ],
                cwd=ROOT,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
        state[name] = {"pid": process.pid, "provider": args.provider}
        STATE.write_text(json.dumps(state, indent=2) + "\n")
        STATE.chmod(0o600)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and process.poll() is None:
            if health(port, path):
                break
            time.sleep(0.2)
        else:
            raise SystemExit(f"{name} failed readiness; inspect .local/{name}.log")
    print(f"Local workspace: http://127.0.0.1:8510 · provider={args.provider}")


if __name__ == "__main__":
    main()
