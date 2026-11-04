"""Run browser acceptance against disposable databases, preserving demo inventory."""

import json
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
import psycopg
from database import admin_settings
from psycopg import sql
from sqlalchemy.engine import make_url

from commerce.config import Settings

ROOT = Path(__file__).resolve().parents[1]


def main():
    for port in (8530, 8531):
        try:
            connection = socket.create_connection(("127.0.0.1", port), timeout=0.2)
        except OSError:
            continue
        connection.close()
        raise SystemExit("Browser-check ports are occupied; no existing process was stopped.")
    settings, admin = Settings(), admin_settings()
    url = make_url(admin.database_url)
    if url.host != "127.0.0.1" or url.database != "commerce":
        raise SystemExit("Browser fixtures require the local commerce admin database.")
    names = ["commerce_browser_" + uuid.uuid4().hex[:12] + "_" + kind for kind in ("app", "source")]
    evidence = ROOT / ".local/evidence"
    evidence.mkdir(parents=True, exist_ok=True, mode=0o700)
    environment = dict(os.environ)
    environment.update(
        {
            "COMMERCE_DATABASE_URL": url.set(database=names[0]).render_as_string(
                hide_password=False
            ),
            "COMMERCE_SIMULATOR_DATABASE_URL": url.set(database=names[1]).render_as_string(
                hide_password=False
            ),
            "COMMERCE_SIMULATOR_URL": "http://127.0.0.1:8531",
            "COMMERCE_PUBLIC_BASE_URL": "http://127.0.0.1:8530",
            "COMMERCE_BROWSER_BASE_URL": "http://127.0.0.1:8530",
            "COMMERCE_MODEL_PROVIDER": "baseline",
            "COMMERCE_AUTH_MODE": "demo",
            "COMMERCE_SCHEMA_BOOTSTRAP": "true",
            "COMMERCE_TRACE_ENABLED": "false",
            "COMMERCE_SIGNING_KEY": settings.signing_key.get_secret_value()
            or "isolated-browser-signing-key-only-" * 2,
            "COMMERCE_SOURCE_TOKEN": settings.source_token.get_secret_value()
            or "isolated-browser-source-token-only-" * 2,
            "COMMERCE_ALLOWED_ORIGINS": json.dumps(["http://127.0.0.1:8530"]),
        }
    )
    processes = []
    created = []
    log = None
    with psycopg.connect(
        url.set(drivername="postgresql", database="postgres").render_as_string(hide_password=False),
        autocommit=True,
    ) as connection:
        try:
            for name in names:
                connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
                created.append(name)
            subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=ROOT,
                env=environment,
                check=True,
            )
            log_path = evidence / "browser-services.log"
            log_path.touch(mode=0o600)
            log_path.chmod(0o600)
            log = log_path.open("ab")
            for module, port, path in (
                ("commerce.simulator:create_source_app", 8531, "/health"),
                ("commerce.api:create_app", 8530, "/health/ready"),
            ):
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        module,
                        "--factory",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(port),
                        "--no-access-log",
                    ],
                    cwd=ROOT,
                    env=environment,
                    stdout=log,
                    stderr=log,
                )
                processes.append(process)
                with httpx.Client(trust_env=False, timeout=1) as client:
                    for _ in range(100):
                        try:
                            if client.get(f"http://127.0.0.1:{port}{path}").status_code == 200:
                                break
                        except httpx.HTTPError:
                            pass
                        if process.poll() is not None:
                            raise RuntimeError(
                                "Browser fixture service failed; inspect private log"
                            )
                        time.sleep(0.1)
                    else:
                        raise RuntimeError("Browser fixture service readiness timed out")
            subprocess.run(
                ["npm", "run", "test:e2e", "--prefix", "web"], cwd=ROOT, env=environment, check=True
            )
            print(
                "Browser acceptance passed against disposable synthetic databases; main inventory/history unchanged."
            )
        finally:
            for process in reversed(processes):
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            if log:
                log.close()
            for name in reversed(created):
                if not name.startswith("commerce_browser_"):
                    raise RuntimeError("Unsafe cleanup target")
                connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))


if __name__ == "__main__":
    main()
