"""Run browser acceptance against disposable databases, preserving demo inventory."""

import argparse
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--product", choices=["retail", "pharmacy"], default="retail")
    parser.add_argument("--with-voice", action="store_true")
    parser.add_argument("--record-demo", action="store_true")
    parser.add_argument("--provider", choices=["baseline", "codex"], default="baseline")
    args = parser.parse_args()
    if args.provider == "codex" and not args.record_demo:
        parser.error(
            "Paid-allowance inference is limited to the explicitly requested demo recording."
        )
    if args.record_demo:
        args.product, args.with_voice = "pharmacy", True
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
            "COMMERCE_MODEL_PROVIDER": args.provider,
            "COMMERCE_AUTH_MODE": "demo",
            "COMMERCE_PRODUCT_MODE": args.product,
            "COMMERCE_BROWSER_PRODUCT": args.product,
            "COMMERCE_PHARMACY_DEMO_MINUTE": "1085",
            "COMMERCE_SCHEMA_BOOTSTRAP": "true",
            "COMMERCE_TRACE_ENABLED": "false",
            "COMMERCE_SIGNING_KEY": settings.signing_key.get_secret_value()
            or "isolated-browser-signing-key-only-" * 2,
            "COMMERCE_SOURCE_TOKEN": settings.source_token.get_secret_value()
            or "isolated-browser-source-token-only-" * 2,
            "COMMERCE_ALLOWED_ORIGINS": json.dumps(["http://127.0.0.1:8530"]),
        }
    )
    if args.provider == "codex":
        # Disposable business fixtures still charge the normal durable allowance.
        environment["COMMERCE_MODEL_BUDGET_DATABASE_URL"] = settings.database_url
    if args.with_voice:
        environment["COMMERCE_TEST_VOICE"] = "1"
        environment["COMMERCE_TEST_AUDIO"] = str(ROOT / ".local/voice/fake-capture.wav")
        if Path(settings.tts_python).is_file() and Path(settings.tts_model).is_dir():
            environment["COMMERCE_TEST_NEURAL_VOICE"] = "1"
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
            command = (
                ["node", "tools/record_pharmacy_demo.mjs"]
                if args.record_demo
                else ["npm", "run", "test:e2e", "--prefix", "web"]
            )
            subprocess.run(command, cwd=ROOT, env=environment, check=True)
            if args.record_demo:
                recordings = sorted(
                    (ROOT / ".local/demos").glob("*/recording.json"),
                    key=lambda p: p.stat().st_mtime,
                )
                directory = recordings[-1].parent
                with psycopg.connect(
                    url.set(drivername="postgresql", database=names[0]).render_as_string(
                        hide_password=False
                    )
                ) as fixture:
                    decisions = fixture.execute(
                        "SELECT data FROM audit_events WHERE event_type = 'pharmacy.intent_understood' ORDER BY created_at"
                    ).fetchall()
                    requests = fixture.execute(
                        "SELECT state, provider FROM pharmacy_pickup_requests ORDER BY created_at"
                    ).fetchall()
                with psycopg.connect(
                    url.set(drivername="postgresql", database=names[1]).render_as_string(
                        hide_password=False
                    )
                ) as fixture:
                    commands = fixture.execute(
                        "SELECT action, count(*) FROM source_commands GROUP BY action ORDER BY action"
                    ).fetchall()
                (directory / "backend-evidence.json").write_text(
                    json.dumps(
                        {
                            "decisions": [d[0] for d in decisions],
                            "requests": [
                                {"state": state, "provider": provider}
                                for state, provider in requests
                            ],
                            "source_commands": dict(commands),
                        },
                        indent=2,
                    )
                )
            print(
                "Browser journey completed against disposable synthetic databases; main inventory/history unchanged."
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
