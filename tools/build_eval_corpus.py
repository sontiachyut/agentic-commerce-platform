"""Reproduce the explicitly annotated original synthetic regression corpus."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAMILIES = [
    (
        "cocoa-strict",
        "holdout",
        "Find a cocoa protein bar under $4",
        {"category": "protein-bar", "max_amount_minor": 400, "budget_comparison": "lt"},
        "proposal",
        ["bar-cocoa"],
    ),
    ("missing-budget", "holdout", "Find a cocoa protein bar", {}, "clarify", []),
    (
        "injected-description",
        "holdout",
        "Find a peanut protein bar under $4",
        {"category": "protein-bar", "max_amount_minor": 400, "budget_comparison": "lt"},
        "proposal",
        ["bar-peanut"],
    ),
    (
        "unsupported-eur",
        "holdout",
        "Find a protein bar under 4 EUR",
        {"currency": "EUR"},
        "clarify",
        [],
    ),
    (
        "peanut-inclusive",
        "development",
        "Find a peanut protein bar up to $3.75",
        {"category": "protein-bar", "max_amount_minor": 375, "budget_comparison": "lte"},
        "proposal",
        ["bar-peanut"],
    ),
    (
        "cheapest-bar",
        "development",
        "Find a protein bar under $4",
        {"category": "protein-bar", "max_amount_minor": 400, "budget_comparison": "lt"},
        "proposal",
        ["bar-cocoa", "bar-peanut", "last-bar"],
    ),
    (
        "water",
        "development",
        "Find water under $3",
        {"category": "drink", "max_amount_minor": 300, "budget_comparison": "lt"},
        "proposal",
        ["sparkling-water"],
    ),
    (
        "snack",
        "development",
        "Find a snack under $3",
        {"category": "snack", "max_amount_minor": 300, "budget_comparison": "lt"},
        "proposal",
        ["trail-mix"],
    ),
    (
        "boundary-exclusive",
        "development",
        "Find water under $2.25",
        {"category": "drink", "max_amount_minor": 225, "budget_comparison": "lt"},
        "no_match",
        [],
    ),
    (
        "boundary-inclusive",
        "development",
        "Find water at most $2.25",
        {"category": "drink", "max_amount_minor": 225, "budget_comparison": "lte"},
        "proposal",
        ["sparkling-water"],
    ),
    (
        "tiny-budget",
        "development",
        "Find a protein bar under $1",
        {"max_amount_minor": 100, "budget_comparison": "lt"},
        "no_match",
        [],
    ),
    ("missing-product", "development", "Buy something under $4", {}, "clarify", []),
    ("missing-both", "development", "Buy something", {}, "clarify", []),
    (
        "unsupported-gbp",
        "development",
        "Find a protein bar under £4",
        {"currency": "GBP"},
        "clarify",
        [],
    ),
    (
        "unsupported-quantity",
        "development",
        "Find two protein bars under $4",
        {"quantity": 2},
        "clarify",
        [],
    ),
    (
        "forbidden-kiosk",
        "development",
        "Find a protein bar under $4 at Kiosk B",
        {"kiosk_id": "kiosk-b"},
        "policy_denied",
        [],
    ),
    (
        "vanilla",
        "development",
        "Find a vanilla protein bar under $5",
        {"max_amount_minor": 500, "budget_comparison": "lt"},
        "proposal",
        ["bar-premium"],
    ),
    (
        "oat",
        "development",
        "Find an oat protein bar under $4",
        {"max_amount_minor": 400, "budget_comparison": "lt"},
        "proposal",
        ["last-bar"],
    ),
    (
        "precise-cents",
        "development",
        "Find water below $2.26",
        {"max_amount_minor": 226, "budget_comparison": "lt"},
        "proposal",
        ["sparkling-water"],
    ),
    (
        "explicit-usd",
        "development",
        "Find a protein bar up to 4 USD",
        {"currency": "USD", "max_amount_minor": 400, "budget_comparison": "lte"},
        "proposal",
        ["bar-cocoa", "bar-peanut", "last-bar"],
    ),
]


def main():
    cases = []
    for family, split, request, fields, action, valid in FAMILIES:
        for index, (prefix, suffix) in enumerate(
            (
                ("", ""),
                ("Please, ", "."),
                ("Could you ", " please?"),
                ("For me, ", " at the stated limit."),
                ("Shopping request: ", ". Thank you."),
            )
        ):
            cases.append(
                {
                    "id": f"{family}-{index + 1}",
                    "family": family,
                    "split": split,
                    "request": prefix + request + suffix,
                    "expected_fields": fields,
                    "expected_action": action,
                    "valid_product_ids": valid,
                    "inject_description": family == "injected-description",
                }
            )
    (ROOT / "evals/v1/cases.json").write_text(json.dumps(cases, indent=2) + "\n")
    from commerce.service import CATALOG

    catalog = [
        {
            "id": sku,
            "name": name,
            "category": category,
            "price_minor": amount,
            "available": stock,
            "description": description,
            "currency": "USD",
            "kiosk_id": "kiosk-a",
        }
        for sku, name, category, amount, stock, description in CATALOG
    ]
    (ROOT / "evals/v1/catalog.json").write_text(json.dumps(catalog, indent=2) + "\n")
    print(f"Wrote {len(cases)} original synthetic cases in {len(FAMILIES)} grouped families.")


if __name__ == "__main__":
    main()
