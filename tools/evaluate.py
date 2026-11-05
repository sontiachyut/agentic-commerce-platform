"""Versioned decision evaluation without financial side effects or oracle leakage."""

import argparse
import hashlib
import json
import secrets
from datetime import UTC, datetime
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver

from commerce.agent import ShoppingAgent
from commerce.config import Settings
from commerce.db import make_engine, make_sessions
from commerce.evaluation import reserve_evaluation_session, run_case
from commerce.models import PurchaseSession
from commerce.planner import BaselinePlanner, CodexPlanner, ModelUnavailable
from commerce.schemas import Actor
from commerce.service import CommerceService

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["baseline", "codex"], default="baseline")
    parser.add_argument("--split", choices=["all", "development", "holdout"], default="all")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--resume", type=Path)
    args = parser.parse_args()
    if not 1 <= args.limit <= (8 if args.provider == "codex" else 1000):
        raise SystemExit("Limit must be positive; real-model batches are bounded to eight cases.")
    corpus = ROOT / "evals/v1/cases.json"
    catalog = json.loads((ROOT / "evals/v1/catalog.json").read_text())
    cases = [
        case
        for case in json.loads(corpus.read_text())
        if args.split == "all" or case["split"] == args.split
    ]
    # Round-robin families ensures small real batches don't cover only paraphrases.
    cases.sort(key=lambda case: (int(case["id"].rsplit("-", 1)[1]), case["family"]))
    cases = cases[: args.limit]
    run = args.resume or ROOT / "results/evaluations" / (
        datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + args.provider
        + "-"
        + secrets.token_hex(3)
    )
    run.mkdir(parents=True, exist_ok=args.resume is not None)
    manifest = {
        "provider": args.provider,
        "split": args.split,
        "case_ids": [c["id"] for c in cases],
        "corpus_sha256": hashlib.sha256(corpus.read_bytes()).hexdigest(),
        "catalog_sha256": hashlib.sha256((ROOT / "evals/v1/catalog.json").read_bytes()).hexdigest(),
        "planner_sha256": hashlib.sha256(
            (ROOT / "src/commerce/planner.py").read_bytes()
        ).hexdigest(),
        "schema_sha256": hashlib.sha256(
            (ROOT / "src/commerce/schemas.py").read_bytes()
        ).hexdigest(),
        "scope": "Decision-only synthetic regression; no purchases; not representative accuracy or model tool-selection evidence.",
    }
    manifest_file = run / "manifest.json"
    if manifest_file.exists() and json.loads(manifest_file.read_text()) != manifest:
        raise SystemExit("Resume configuration/corpus differs")
    manifest_file.write_text(json.dumps(manifest, indent=2) + "\n")
    settings = Settings()
    planner = CodexPlanner(settings) if args.provider == "codex" else BaselinePlanner()
    engine = make_engine(settings.database_url)
    service = CommerceService(make_sessions(engine), settings)
    agent = ShoppingAgent(service, planner, InMemorySaver(), engine)
    actor = Actor(user_id="evaluation", tenant_id="eval")
    results_file = run / "cases.jsonl"
    results = (
        [json.loads(line) for line in results_file.read_text().splitlines()]
        if results_file.exists()
        else []
    )
    done = {r["case_id"] for r in results}
    try:
        for case in cases:
            if case["id"] in done:
                continue
            session = None
            try:
                if args.provider == "codex":
                    session = reserve_evaluation_session(
                        service, actor, case["request"], "eval:" + run.name + ":" + case["id"]
                    )
                result = run_case(
                    planner,
                    case,
                    catalog,
                    (
                        lambda purpose, session_id=session: agent.reserve_model_call(
                            session_id, purpose
                        )
                    )
                    if session
                    else (lambda purpose: None),
                )
            except ModelUnavailable as exc:
                result = {
                    "case_id": case["id"],
                    "passed": False,
                    "error": type(exc).__name__,
                    "reason": "Model unavailable, deadline or allowance limit; not retried automatically.",
                }
            finally:
                if session:
                    with service.factory.begin() as db:
                        db.get(PurchaseSession, session).state = "EVALUATED"
            with results_file.open("a") as output:
                output.write(json.dumps(result) + "\n")
                output.flush()
            results.append(result)
            print(f"{case['id']}: {'PASS' if result['passed'] else 'FAIL'}", flush=True)
            if result.get("error"):
                break
    finally:
        engine.dispose()
    summary = {
        "requested": len(cases),
        "executed": len(results),
        "passed": sum(r["passed"] for r in results),
        "failed": sum(not r["passed"] for r in results),
        "provider": args.provider,
        "complete": len(results) == len(cases),
        "financial_side_effects": 0,
        "elapsed_seconds": round(sum(r.get("elapsed_seconds", 0) for r in results), 3),
    }
    (run / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    print(run.relative_to(ROOT))


if __name__ == "__main__":
    main()
