import re
from decimal import Decimal

from commerce.pharmacy.schemas import FamilyIntent
from commerce.planner import CodexPlanner


class FamilyBaseline:
    name = "baseline"

    def family_intent(self, text):
        lower = text.lower()
        aliases = {
            "self": r"\b(myself|me|my regular|for myself)\b",
            "dad": r"\b(dad|father)\b",
            "mom": r"\b(mom|mum|mother)\b",
            "sister": r"\bsister\b",
        }
        members = [alias for alias, pattern in aliases.items() if re.search(pattern, lower)]
        if re.search(r"\b(family|everyone|whole household)\b", lower):
            members = list(aliases)
        if "parents" in lower:
            members = list(dict.fromkeys(members + ["dad", "mom"]))
        for word, number in [
            ("fifty", "50"),
            ("forty five", "45"),
            ("forty", "40"),
            ("thirty", "30"),
            ("twenty", "20"),
        ]:
            lower = lower.replace(word, number)
        amount = re.search(
            r"(?:under|below|up to|at most|limit|budget)\s*\$?\s*(\d+(?:\.\d{1,2})?)", lower
        )
        maximum = int(Decimal(amount.group(1)) * 100) if amount else None
        currency = (
            "EUR"
            if "eur" in lower or "€" in lower
            else "GBP"
            if "gbp" in lower or "£" in lower
            else "USD"
        )
        clarification = None
        if not members:
            clarification = "Who should I include: you, Dad, Mom or your sister?"
        elif not maximum:
            clarification = "What is the maximum total for this family pickup?"
        elif currency != "USD":
            clarification = "This pharmacy demo supports USD. What USD limit should I use?"
        return FamilyIntent(
            members=members,
            max_amount_minor=maximum,
            budget_comparison="lt" if re.search(r"\b(under|below|less than)\b", lower) else "lte",
            currency=currency,
            location="nearest_home",
            clarification=clarification,
        )


class FamilyCodex(CodexPlanner):
    decision_domain = "pharmacy"

    def family_intent(self, text):
        return self._infer(
            "Extract a family pharmacy pickup request. Resolve only explicitly requested household aliases. "
            "The word family/everyone means all listed aliases; parents means dad and mom. "
            "Use nearest_home for the saved home destination. Require a maximum total; understand spoken number words. "
            "Ask clarification for missing people/budget, unsupported tasks, currencies, substitutions or medical advice. "
            "Do not choose medicines, make clinical judgments or create spending permission. "
            "Return only the defined fields, with location=nearest_home when not otherwise stated.",
            {
                "request": text,
                "known_aliases": ["self", "dad", "mom", "sister"],
                "supported_currency": "USD",
                "default_location": "nearest_home",
            },
            FamilyIntent,
        )
