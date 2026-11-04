"""Rehearse local migrations and restore into uniquely named disposable databases.

Never restore over commerce/source state. The API and simulator must be stopped.
"""

import hashlib
import json
import os
import socket
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

from commerce.config import get_settings

ROOT = Path(__file__).resolve().parents[1]


def local_url(value, expected):
    url = make_url(value)
    if url.host != "127.0.0.1" or url.port != 55439 or url.database != expected:
        raise SystemExit("Restore rehearsal requires the default isolated local Compose databases.")
    return url


def fingerprint(url):
    result = {}
    with psycopg.connect(
        url.set(drivername="postgresql").render_as_string(hide_password=False)
    ) as db:
        tables = db.execute("""
            SELECT schemaname, tablename FROM pg_tables
            WHERE schemaname IN ('public', 'agent_checkpoints')
            ORDER BY schemaname, tablename
        """).fetchall()
        for schema, table in tables:
            rows = db.execute(
                sql.SQL(
                    "SELECT row_to_json(t)::text FROM {}.{} t ORDER BY row_to_json(t)::text"
                ).format(sql.Identifier(schema), sql.Identifier(table))
            ).fetchall()
            hasher = hashlib.sha256()
            for (row,) in rows:
                hasher.update(row.encode())
                hasher.update(b"\n")
            result[f"{schema}.{table}"] = {"rows": len(rows), "sha256": hasher.hexdigest()}
    return result


def main():
    os.chdir(ROOT)
    for port in (8510, 8511):
        try:
            connection = socket.create_connection(("127.0.0.1", port), timeout=0.5)
        except OSError:
            continue
        connection.close()
        raise SystemExit("Stop the API and source with tools/stack.py down before rehearsal.")
    settings = get_settings()
    commerce = local_url(settings.database_url, "commerce")
    source = local_url(settings.simulator_database_url, "commerce_sources")
    suffix = uuid.uuid4().hex[:10]
    names = [f"commerce_rehearsal_{suffix}_{kind}" for kind in ("migration", "restore", "source")]
    directory = ROOT / ".local" / "backups" / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    directory.mkdir(parents=True, mode=0o700)
    directory.chmod(0o700)
    log = directory / "rehearsal.log"
    log.touch(mode=0o600)
    compose = ["docker", "compose", "-p", "agentic-commerce", "exec", "-T", "postgres"]
    created = []
    report = {"recorded_at": datetime.now(UTC).isoformat(), "migrations": {}, "restores": {}}
    with psycopg.connect(
        commerce.set(drivername="postgresql", database="postgres").render_as_string(
            hide_password=False
        ),
        autocommit=True,
    ) as admin:
        try:
            for name in names:
                admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
                created.append(name)
            environment = dict(os.environ)
            environment["COMMERCE_DATABASE_URL"] = commerce.set(database=names[0]).render_as_string(
                hide_password=False
            )
            with log.open("ab") as output:
                for arguments in (
                    ["upgrade", "head"],
                    ["check"],
                    ["downgrade", "base"],
                    ["upgrade", "head"],
                    ["check"],
                ):
                    subprocess.run(
                        [sys.executable, "-m", "alembic", *arguments],
                        env=environment,
                        stdout=output,
                        stderr=output,
                        check=True,
                    )
            report["migrations"] = {
                "fresh_upgrade": True,
                "downgrade_base": True,
                "second_upgrade": True,
                "metadata_check": True,
            }
            for original, target in ((commerce, names[1]), (source, names[2])):
                dump = directory / f"{original.database}.dump"
                dump.touch(mode=0o600)
                before = fingerprint(original)
                with dump.open("wb") as destination, log.open("ab") as output:
                    subprocess.run(
                        compose + ["pg_dump", "-U", "commerce", "-Fc", original.database],
                        stdout=destination,
                        stderr=output,
                        check=True,
                    )
                with dump.open("rb") as backup, log.open("ab") as output:
                    subprocess.run(
                        compose
                        + [
                            "pg_restore",
                            "--exit-on-error",
                            "--no-owner",
                            "--no-acl",
                            "-U",
                            "commerce",
                            "-d",
                            target,
                        ],
                        stdin=backup,
                        stdout=output,
                        stderr=output,
                        check=True,
                    )
                after = fingerprint(original.set(database=target))
                if before != after:
                    raise RuntimeError(
                        "Restored table fingerprints differ; inspect private rehearsal evidence."
                    )
                report["restores"][original.database] = {"matching": True, "tables": before}
        finally:
            for name in reversed(created):
                admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
    evidence = ROOT / ".local" / "evidence" / "restore-rehearsal.json"
    evidence.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    evidence.touch(mode=0o600)
    evidence.write_text(json.dumps(report, indent=2) + "\n")
    print("Fresh migration, downgrade/upgrade, and both independent database restores passed.")
    print("Restored rows matched per-table fingerprints; only rehearsal databases were removed.")
    print("Private backups and report retained under .local/.")


if __name__ == "__main__":
    main()
