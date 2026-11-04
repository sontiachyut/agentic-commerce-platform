"""Prepare private container configuration for the existing synthetic databases."""

import json
import subprocess
from pathlib import Path

from database import private_write
from sqlalchemy.engine import make_url

from commerce.config import Settings

ROOT = Path(__file__).resolve().parents[1]


def main():
    settings = Settings()
    if settings.schema_bootstrap:
        raise SystemExit(
            "Configure least-privilege runtime roles first: tools/database.py configure"
        )
    network = json.loads(
        subprocess.check_output(
            ["docker", "network", "inspect", "agentic-commerce_default"], text=True
        )
    )[0]
    subnets = [entry["Subnet"] for entry in network["IPAM"]["Config"] if "Subnet" in entry]
    destination = ROOT / ".local/packaged"
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination.chmod(0o700)
    api = {
        "COMMERCE_DATABASE_URL": make_url(settings.database_url)
        .set(host="postgres", port=5432)
        .render_as_string(hide_password=False),
        "COMMERCE_SIGNING_KEY": settings.signing_key.get_secret_value(),
        "COMMERCE_SOURCE_TOKEN": settings.source_token.get_secret_value(),
        "COMMERCE_METRICS_TOKEN": settings.metrics_token.get_secret_value(),
        "COMMERCE_MODEL_PROVIDER": "baseline",
        "COMMERCE_AUTH_MODE": "demo",
        "COMMERCE_SCHEMA_BOOTSTRAP": "false",
        "COMMERCE_SIMULATOR_URL": "http://packaged-source:8511",
        "COMMERCE_PUBLIC_BASE_URL": "http://127.0.0.1:8520",
        "COMMERCE_ALLOWED_ORIGINS": json.dumps(["http://127.0.0.1:8520"]),
        "COMMERCE_ALLOWED_CLIENT_CIDRS": json.dumps(subnets + ["127.0.0.1/32", "::1/128"]),
    }
    import platform

    if platform.system() == "Darwin" and platform.machine() == "arm64":
        engine_version = subprocess.check_output(
            ["docker", "version", "--format", "{{.Server.Version}}"], text=True
        ).strip()
        if int(engine_version.split(".")[0]) < 23:
            # Verified old Desktop ARM guest compatibility; do not force this on current production hosts.
            api["OPENSSL_armcap"] = "0"
    source = {
        "COMMERCE_SIMULATOR_DATABASE_URL": make_url(settings.simulator_database_url)
        .set(host="postgres", port=5432)
        .render_as_string(hide_password=False),
        "COMMERCE_SOURCE_TOKEN": settings.source_token.get_secret_value(),
        "COMMERCE_SCHEMA_BOOTSTRAP": "false",
    }
    for name, values in (("api", api), ("source", source)):
        private_write(
            destination / (name + ".env"),
            "\n".join(key + "=" + value for key, value in values.items()) + "\n",
        )
    print(
        "Private container configuration prepared. No model authentication was copied. Packaged demo uses the rule baseline."
    )


if __name__ == "__main__":
    main()
