import json
from pathlib import Path

from commerce.evaluation import run_case
from commerce.planner import BaselinePlanner
from commerce.schemas import Selection

ROOT = Path(__file__).resolve().parents[1]


def test_original_corpus_has_unique_ids_grouped_splits_and_valid_oracles():
    cases = json.loads((ROOT / "evals/v1/cases.json").read_text())
    catalog = json.loads((ROOT / "evals/v1/catalog.json").read_text())
    assert len(cases) == 100 and len({case["id"] for case in cases}) == 100
    by_family = {}
    for case in cases:
        by_family.setdefault(case["family"], set()).add(case["split"])
        assert set(case["valid_product_ids"]) <= {p["id"] for p in catalog}
    assert len(by_family) == 20 and all(len(splits) == 1 for splits in by_family.values())
    assert all(run_case(BaselinePlanner(), case, catalog)["passed"] for case in cases)


def test_backend_safe_refusal_does_not_make_bad_agent_selection_pass():
    case = json.loads((ROOT / "evals/v1/cases.json").read_text())[0]
    catalog = json.loads((ROOT / "evals/v1/catalog.json").read_text())

    class BadSelection(BaselinePlanner):
        def select(self, intent, candidates):
            assert "valid_product_ids" not in str(candidates)
            return Selection(product_id="invented-sku", reason="Confident but wrong")

    result = run_case(BadSelection(), case, catalog)
    assert not result["passed"] and not result["checks"]["valid_set"]


def test_evaluation_reserves_usage_identity_without_enqueuing_purchase(system):
    from sqlalchemy import select

    from commerce.evaluation import reserve_evaluation_session
    from commerce.models import Execution, Job, PurchaseSession

    identifier = reserve_evaluation_session(
        system.service, system.actor, "Find water under $3", "evaluation-no-shopping-job"
    )
    with system.factory() as db:
        assert db.get(PurchaseSession, identifier).state == "EVALUATING"
        assert not db.scalars(select(Job)).all()
        assert not db.scalars(select(Execution)).all()
