"""Finite real-HTTP smoke run. --provider codex consumes two signed-in decisions."""

import argparse
import json
import time
import uuid
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["baseline", "codex"], default="baseline")
    parser.add_argument("--url", default="http://127.0.0.1:8510")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    started = time.monotonic()
    with httpx.Client(base_url=args.url, timeout=10, trust_env=False) as client:
        health = client.get("/health/ready").raise_for_status().json()
        if health["model_provider"] != args.provider:
            raise SystemExit(
                "Running application has a different provider; refusing an unintended test"
            )
        auth = client.post("/api/v1/auth/demo", json={"persona": "alex"}).raise_for_status().json()
        headers = {
            "X-CSRF-Token": auth["csrf_token"],
            "Idempotency-Key": "smoke-" + str(uuid.uuid4()),
        }
        identifier = (
            client.post(
                "/api/v1/sessions",
                json={"request": "Find a cocoa protein bar under $4 at Kiosk A"},
                headers=headers,
            )
            .raise_for_status()
            .json()["session_id"]
        )
        while time.monotonic() - started < 280:
            session = client.get(f"/api/v1/sessions/{identifier}").raise_for_status().json()
            if session["state"] == "AWAITING_APPROVAL":
                quote = session["quote"]
                approval = (
                    client.post(
                        f"/api/v1/quotes/{quote['id']}/approval",
                        json={"quote_digest": quote["digest"]},
                        headers=headers,
                    )
                    .raise_for_status()
                    .json()
                )
                headers["Idempotency-Key"] = "smoke-execute-" + identifier
                request = {
                    "quote_id": quote["id"],
                    "approval_id": approval["id"],
                    "fault_profile": "payment_response_lost",
                }
                first = (
                    client.post("/api/v1/executions", json=request, headers=headers)
                    .raise_for_status()
                    .json()
                )
                duplicate = (
                    client.post("/api/v1/executions", json=request, headers=headers)
                    .raise_for_status()
                    .json()
                )
                assert first["id"] == duplicate["id"]
                break
            if session["state"] not in {"QUEUED"}:
                raise SystemExit(f"Shopping did not reach approval: {session['state']}")
            time.sleep(0.25)
        else:
            raise SystemExit("Shopping decision deadline exceeded")
        while time.monotonic() - started < 300:
            session = client.get(f"/api/v1/sessions/{identifier}").raise_for_status().json()
            if session["state"] == "COMPLETED":
                assert session["execution"]["outcome"]["success"]
                usage = [
                    e["data"].get("usage", {})
                    for e in session["events"]
                    if e["type"] in {"agent.intent", "agent.selection"}
                ]
                report = {
                    "provider": args.provider,
                    "session_id": identifier,
                    "execution_id": first["id"],
                    "duplicate_execution_same_id": True,
                    "outcome": session["execution"]["outcome"],
                    "model_usage": usage,
                    "events": [e["type"] for e in session["events"]],
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
                if args.output:
                    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    args.output.write_text(json.dumps(report, indent=2) + "\n")
                    args.output.chmod(0o600)
                print(json.dumps(report, indent=2))
                return
            if session["state"] in {"CANCELED", "RECOVERY_REQUIRED", "POLICY_DENIED"}:
                raise SystemExit(f"Purchase did not complete: {session['state']}")
            time.sleep(0.25)
    raise SystemExit("Execution deadline exceeded")


if __name__ == "__main__":
    main()
