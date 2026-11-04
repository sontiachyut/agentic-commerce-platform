"""Explicit local development lifecycle. Never creates billable resources."""

import argparse
import os
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["init", "seed", "api", "source", "worker"])
    args = parser.parse_args()
    os.chdir(ROOT)
    if args.command == "init":
        path = ROOT / ".env"
        if not path.exists():
            with open(path, "x", opener=lambda name, flags: os.open(name, flags, 0o600)) as f:
                f.write("COMMERCE_SIGNING_KEY=" + secrets.token_urlsafe(48) + "\n")
                f.write("COMMERCE_SOURCE_TOKEN=" + secrets.token_urlsafe(48) + "\n")
                f.write("COMMERCE_METRICS_TOKEN=" + secrets.token_urlsafe(48) + "\n")
                f.write("COMMERCE_MODEL_PROVIDER=baseline\n")
        print(
            "Local configuration ready. Secrets were not printed. Start PostgreSQL and run alembic upgrade head."
        )
        return
    if args.command == "seed":
        from commerce.config import get_settings
        from commerce.db import make_engine, make_sessions
        from commerce.service import seed

        seed(make_sessions(make_engine(get_settings().database_url)))
        print("Synthetic catalog seeded without overwriting existing inventory.")
        return
    module = (
        "commerce.api:create_app"
        if args.command == "api"
        else "commerce.simulator:create_source_app"
    )
    if args.command == "worker":
        raise SystemExit(
            "The v0.1 worker runs with the API. Multi-process API is serialized at the graph boundary."
        )
    port = "8510" if args.command == "api" else "8511"
    subprocess.run(
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
            port,
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
