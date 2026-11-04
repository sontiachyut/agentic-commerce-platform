"""Bundle pinned official schemas offline, preserving their licenses and provenance."""

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "src/commerce/protocol_schemas"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ucp", type=Path, required=True)
    parser.add_argument("--acp", type=Path, required=True)
    parser.add_argument("--compiler", type=Path, required=True)
    args = parser.parse_args()
    manifest = {
        "ucp": {"version": "2026-08-25", "revision": "87dd4b1fcff9105d68173120897237fa784c74ef"},
        "acp": {"version": "2026-04-17", "revision": "7fdd78df677a94dce04c770644b0fbbb1401272b"},
        "compiler": "ucp-schema 1.4.1",
        "files": {},
    }
    compiler = str(args.compiler.resolve())
    if subprocess.check_output([compiler, "--version"], text=True).strip() != "ucp-schema 1.4.1":
        raise SystemExit("Use pinned compiler 1.4.1")
    for name, source in (("ucp", args.ucp), ("acp", args.acp)):
        receipt = source / "RESEARCH_MANIFEST.json"
        if receipt.exists():
            # Snapshot receipts may include additional metadata; exact input hashes below remain authoritative.
            data = json.loads(receipt.read_text())
            observed = data.get("commit") or data.get("revision")
        else:
            observed = subprocess.check_output(
                ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
            ).strip()
        if observed and observed != manifest[name]["revision"]:
            raise SystemExit("Source revision mismatch: " + name)
        (DEST / name).mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / "LICENSE", DEST / name / "LICENSE")
    schemas = args.ucp.resolve() / "source/schemas"
    for operation in ("create", "update", "read", "complete", "cancel"):
        for direction in ("request", "response"):
            target = DEST / "ucp" / f"{operation}_{direction}.json"
            subprocess.run(
                [
                    compiler,
                    "resolve",
                    str(schemas / "shopping/checkout.json"),
                    "--" + direction,
                    "--op",
                    operation,
                    "--bundle",
                    "--pretty",
                    "--output",
                    str(target),
                ],
                check=True,
            )
    subprocess.run(
        [
            compiler,
            "resolve",
            str(schemas / "profile.json"),
            "--response",
            "--op",
            "read",
            "--def",
            "business_schema",
            "--bundle",
            "--pretty",
            "--output",
            str(DEST / "ucp/discovery.json"),
        ],
        check=True,
    )
    subprocess.run(
        [
            compiler,
            "resolve",
            str(schemas / "common/payment_ap2_mandate.json"),
            "--request",
            "--op",
            "complete",
            "--def",
            "dev.ucp.shopping.checkout",
            "--bundle",
            "--pretty",
            "--output",
            str(DEST / "ucp/ap2_complete_request.json"),
        ],
        check=True,
    )
    shutil.copyfile(
        args.acp / "spec/2026-04-17/json-schema/schema.agentic_checkout.json",
        DEST / "acp/checkout.json",
    )
    for path in sorted(DEST.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            manifest["files"][str(path.relative_to(DEST))] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    (DEST / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Bundled {len(manifest['files'])} licensed files; no runtime schema fetches.")


if __name__ == "__main__":
    main()
