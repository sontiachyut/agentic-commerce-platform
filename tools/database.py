"""Separate local migration/source provisioning from least-privilege runtime roles."""

import argparse
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

from commerce.config import Settings
from commerce.db import make_engine
from commerce.simulator import SourceBase

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / ".local/database"


def private_write(path, value):
    fd = os.open(path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as output:
        output.write(value)
    path.chmod(0o600)


def admin_settings():
    return (
        Settings(_env_file=PRIVATE / "admin.env")
        if (PRIVATE / "admin.env").exists()
        else Settings()
    )


def provision():
    settings = admin_settings()
    urls = [make_url(settings.database_url), make_url(settings.simulator_database_url)]
    if [(url.host, url.port, url.database) for url in urls] != [
        ("127.0.0.1", 55439, "commerce"),
        ("127.0.0.1", 55439, "commerce_sources"),
    ]:
        raise SystemExit("Provisioning is restricted to this project’s local synthetic databases.")
    PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    PRIVATE.chmod(0o700)
    credential_file = PRIVATE / "credentials.json"
    credentials = (
        json.loads(credential_file.read_text())
        if credential_file.exists()
        else {name: secrets.token_urlsafe(36) for name in ("commerce_app", "commerce_source")}
    )
    private_write(credential_file, json.dumps(credentials, indent=2) + "\n")
    private_write(
        PRIVATE / "admin.env",
        "COMMERCE_DATABASE_URL="
        + settings.database_url
        + "\nCOMMERCE_SIMULATOR_DATABASE_URL="
        + settings.simulator_database_url
        + "\n",
    )
    # Provision source/checkpoint schemas with the migration identity, never at runtime.
    source_engine = make_engine(settings.simulator_database_url)
    SourceBase.metadata.create_all(source_engine)
    source_engine.dispose()
    from langgraph.checkpoint.postgres import PostgresSaver

    with psycopg.connect(
        urls[0].set(drivername="postgresql").render_as_string(hide_password=False),
        autocommit=True,
        prepare_threshold=0,
    ) as connection:
        connection.execute("CREATE SCHEMA IF NOT EXISTS agent_checkpoints")
        connection.execute("SET search_path TO agent_checkpoints")
        PostgresSaver(connection).setup()
    for url, role, schemas in (
        (urls[0], "commerce_app", ("public", "agent_checkpoints")),
        (urls[1], "commerce_source", ("public",)),
    ):
        with psycopg.connect(
            url.set(drivername="postgresql").render_as_string(hide_password=False), autocommit=True
        ) as db:
            if not db.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
                db.execute(
                    sql.SQL(
                        "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION"
                    ).format(sql.Identifier(role), sql.Literal(credentials[role]))
                )
            db.execute(
                sql.SQL("REVOKE CONNECT ON DATABASE {} FROM PUBLIC").format(
                    sql.Identifier(url.database)
                )
            )
            db.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(url.database), sql.Identifier(role)
                )
            )
            for schema in schemas:
                db.execute(
                    sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                        sql.Identifier(schema), sql.Identifier(role)
                    )
                )
                db.execute(
                    sql.SQL("GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA {} TO {}").format(
                        sql.Identifier(schema), sql.Identifier(role)
                    )
                )
                db.execute(
                    sql.SQL("GRANT USAGE ON ALL SEQUENCES IN SCHEMA {} TO {}").format(
                        sql.Identifier(schema), sql.Identifier(role)
                    )
                )
    changes = {
        "COMMERCE_DATABASE_URL": urls[0]
        .set(username="commerce_app", password=credentials["commerce_app"])
        .render_as_string(hide_password=False),
        "COMMERCE_SIMULATOR_DATABASE_URL": urls[1]
        .set(username="commerce_source", password=credentials["commerce_source"])
        .render_as_string(hide_password=False),
        "COMMERCE_SCHEMA_BOOTSTRAP": "false",
    }
    env = ROOT / ".env"
    lines = [line for line in env.read_text().splitlines() if line.partition("=")[0] not in changes]
    private_write(
        env, "\n".join(lines + [key + "=" + value for key, value in changes.items()]) + "\n"
    )
    print(
        "Runtime roles configured with table DML only; source/checkpoint schemas provisioned by admin. Credentials stayed private."
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["configure", "migrate", "check"])
    args = parser.parse_args()
    if args.command == "configure":
        provision()
        return
    settings = admin_settings()
    if args.command == "migrate":
        environment = dict(os.environ)
        environment["COMMERCE_DATABASE_URL"] = settings.database_url
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT,
            env=environment,
            check=True,
        )
        if (PRIVATE / "admin.env").exists():
            provision()
    else:
        runtime = Settings()
        for value, table in (
            (runtime.database_url, "products"),
            (runtime.simulator_database_url, "source_commands"),
        ):
            with psycopg.connect(
                make_url(value).set(drivername="postgresql").render_as_string(hide_password=False)
            ) as db:
                role = db.execute(
                    "SELECT rolsuper, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname=current_user"
                ).fetchone()
                if any(role):
                    raise RuntimeError("Runtime role has administrative privileges")
                assert db.execute(
                    "SELECT has_schema_privilege(current_user,'public','CREATE')"
                ).fetchone() == (False,)
                assert db.execute(
                    "SELECT has_table_privilege(current_user,%s,'SELECT,INSERT,UPDATE')", (table,)
                ).fetchone() == (True,)
        print(
            "Both runtime identities can read/write their tables and cannot create schema objects or databases."
        )


if __name__ == "__main__":
    main()
