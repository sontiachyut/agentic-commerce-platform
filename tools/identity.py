"""Provision the isolated local identity provider; never print credentials."""

import argparse
import json
import os
import secrets
import subprocess
from pathlib import Path

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / ".local/identity"


def write_private(path, text):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(text)
    path.chmod(0o600)


def client_scopes():
    def mapper(name, kind, config):
        return {
            "name": name,
            "protocol": "openid-connect",
            "protocolMapper": kind,
            "config": config,
        }

    return [
        {
            "name": "basic",
            "protocol": "openid-connect",
            "protocolMappers": [
                mapper(
                    "subject",
                    "oidc-sub-mapper",
                    {"access.token.claim": "true", "id.token.claim": "true"},
                )
            ],
        },
        {
            "name": "profile",
            "protocol": "openid-connect",
            "protocolMappers": [
                mapper(
                    "username",
                    "oidc-usermodel-property-mapper",
                    {
                        "user.attribute": "username",
                        "claim.name": "preferred_username",
                        "jsonType.label": "String",
                        "id.token.claim": "true",
                        "access.token.claim": "true",
                    },
                )
            ],
        },
        {
            "name": "roles",
            "protocol": "openid-connect",
            "protocolMappers": [
                mapper(
                    "realm roles",
                    "oidc-usermodel-realm-role-mapper",
                    {
                        "multivalued": "true",
                        "claim.name": "realm_access.roles",
                        "jsonType.label": "String",
                        "access.token.claim": "true",
                        "id.token.claim": "true",
                    },
                )
            ],
        },
        *[
            {
                "name": scope,
                "protocol": "openid-connect",
                "attributes": {"include.in.token.scope": "true"},
            }
            for scope in ("commerce:read", "commerce:write")
        ],
    ]


def reconcile_scopes():
    # Administrative provisioning only. Application users always use Code + PKCE.
    import time

    import httpx

    credentials = json.loads((PRIVATE / "credentials.json").read_text())
    with httpx.Client(base_url="http://127.0.0.1:8850", trust_env=False, timeout=5) as client:
        for _attempt in range(60):
            try:
                response = client.get("/realms/commerce/.well-known/openid-configuration")
                if response.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        else:
            raise SystemExit("Local identity provider did not become ready")
        response = client.post(
            "/realms/master/protocol/openid-connect/token",
            data={
                "client_id": "admin-cli",
                "grant_type": "password",
                "username": "local-admin",
                "password": credentials["admin"],
            },
        )
        response.raise_for_status()
        client.headers["Authorization"] = "Bearer " + response.json()["access_token"]
        base = "/admin/realms/commerce"
        existing = {
            value["name"]: value["id"] for value in client.get(base + "/client-scopes").json()
        }
        for scope in client_scopes():
            if scope["name"] not in existing:
                response = client.post(base + "/client-scopes", json=scope)
                response.raise_for_status()
        existing = {
            value["name"]: value["id"] for value in client.get(base + "/client-scopes").json()
        }
        for name in ("commerce-web", "commerce-tools"):
            identifier = client.get(base + "/clients", params={"clientId": name}).json()[0]["id"]
            for scope in client_scopes():
                client.put(
                    base
                    + "/clients/"
                    + identifier
                    + "/default-client-scopes/"
                    + existing[scope["name"]]
                ).raise_for_status()
    print("Local identity provider ready; Code + PKCE clients provisioned.")


def initialize():
    PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    PRIVATE.chmod(0o700)
    credentials_file = PRIVATE / "credentials.json"
    if credentials_file.exists():
        credentials = json.loads(credentials_file.read_text())
    else:
        credentials = {
            key: secrets.token_urlsafe(36)
            for key in ("database", "admin", "client", "alex", "sam", "operator", "taylor")
        }
        write_private(credentials_file, json.dumps(credentials, indent=2) + "\n")
    with psycopg.connect(
        "postgresql://commerce:local-demo-only@127.0.0.1:55439/commerce", autocommit=True
    ) as connection:
        if not connection.execute(
            "SELECT 1 FROM pg_roles WHERE rolname='commerce_identity'"
        ).fetchone():
            connection.execute(
                sql.SQL("CREATE ROLE commerce_identity LOGIN PASSWORD {}").format(
                    sql.Literal(credentials["database"])
                )
            )
        if not connection.execute(
            "SELECT 1 FROM pg_database WHERE datname='commerce_identity'"
        ).fetchone():
            connection.execute("CREATE DATABASE commerce_identity OWNER commerce_identity")
    roles = [{"name": "commerce-shopper"}, {"name": "commerce-operator"}]
    users = [
        {
            "username": name,
            "enabled": True,
            "emailVerified": True,
            "firstName": name.title(),
            "lastName": "Synthetic",
            "email": name + "@example.test",
            "attributes": {"tenant_id": ["studio-b" if name == "taylor" else "demo"]},
            "realmRoles": ["commerce-operator" if name == "operator" else "commerce-shopper"],
            "credentials": [{"type": "password", "value": credentials[name], "temporary": False}],
        }
        for name in ("alex", "sam", "operator", "taylor")
    ]
    mappers = [
        {
            "name": "tenant",
            "protocol": "openid-connect",
            "protocolMapper": "oidc-usermodel-attribute-mapper",
            "config": {
                "user.attribute": "tenant_id",
                "claim.name": "tenant_id",
                "jsonType.label": "String",
                "id.token.claim": "true",
                "access.token.claim": "true",
            },
        },
        *[
            {
                "name": audience,
                "protocol": "openid-connect",
                "protocolMapper": "oidc-audience-mapper",
                "config": {
                    "included.custom.audience": audience,
                    "access.token.claim": "true",
                    "id.token.claim": "false",
                },
            }
            for audience in ("commerce-api", "http://127.0.0.1:8510/mcp")
        ],
    ]
    clients = []
    for name, public, callbacks in (
        ("commerce-web", False, ["http://127.0.0.1:8510/api/v1/auth/callback"]),
        ("commerce-tools", True, ["http://127.0.0.1:8859/callback"]),
    ):
        clients.append(
            {
                "clientId": name,
                "enabled": True,
                "protocol": "openid-connect",
                "publicClient": public,
                "secret": credentials["client"] if not public else "",
                "standardFlowEnabled": True,
                "directAccessGrantsEnabled": False,
                "serviceAccountsEnabled": False,
                "redirectUris": callbacks,
                "webOrigins": [],
                "defaultClientScopes": [
                    "basic",
                    "profile",
                    "roles",
                    "commerce:read",
                    "commerce:write",
                ],
                "attributes": {"pkce.code.challenge.method": "S256"},
                "protocolMappers": mappers,
            }
        )
    realm = {
        "realm": "commerce",
        "enabled": True,
        "sslRequired": "none",
        "registrationAllowed": False,
        "resetPasswordAllowed": False,
        "rememberMe": False,
        "accessTokenLifespan": 120,
        "revokeRefreshToken": True,
        "refreshTokenMaxReuse": 0,
        "roles": {"realm": roles},
        "clientScopes": client_scopes(),
        "users": users,
        "clients": clients,
    }
    write_private(PRIVATE / "commerce-realm.json", json.dumps(realm, indent=2) + "\n")
    write_private(
        PRIVATE / "runtime.env",
        "\n".join(
            [
                "KC_DB=postgres",
                "KC_DB_URL=jdbc:postgresql://postgres:5432/commerce_identity",
                "KC_DB_USERNAME=commerce_identity",
                "KC_DB_PASSWORD=" + credentials["database"],
                "KC_BOOTSTRAP_ADMIN_USERNAME=local-admin",
                "KC_BOOTSTRAP_ADMIN_PASSWORD=" + credentials["admin"],
                "KC_HOSTNAME=http://127.0.0.1:8850",
                "KC_HEALTH_ENABLED=true",
                "JAVA_OPTS_KC_HEAP=-Xms128m -Xmx512m",
                "",
            ]
        ),
    )
    env_path = ROOT / ".env"
    lines = env_path.read_text().splitlines()
    additions = {"COMMERCE_AUTH_MODE": "oidc", "COMMERCE_OIDC_CLIENT_SECRET": credentials["client"]}
    lines = [line for line in lines if line.partition("=")[0] not in additions]
    write_private(
        env_path, "\n".join(lines + [f"{key}={value}" for key, value in additions.items()]) + "\n"
    )
    print(
        "Local identity configured. Credentials remain in .local/identity/credentials.json (owner-only)."
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["init", "up", "down"])
    args = parser.parse_args()
    if args.command == "init":
        initialize()
    elif args.command == "up":
        if not (PRIVATE / "runtime.env").exists():
            raise SystemExit("Run init first")
        subprocess.run(
            [
                "docker",
                "compose",
                "-p",
                "agentic-commerce",
                "--profile",
                "identity",
                "run",
                "--rm",
                "--no-deps",
                "identity-seed",
            ],
            cwd=ROOT,
            check=True,
        )
        subprocess.run(
            [
                "docker",
                "compose",
                "-p",
                "agentic-commerce",
                "--profile",
                "identity",
                "up",
                "-d",
                "identity",
            ],
            cwd=ROOT,
            check=True,
        )
        reconcile_scopes()
    else:
        subprocess.run(
            [
                "docker",
                "compose",
                "-p",
                "agentic-commerce",
                "--profile",
                "identity",
                "stop",
                "identity",
            ],
            cwd=ROOT,
            check=True,
        )


if __name__ == "__main__":
    main()
