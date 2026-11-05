from typing import Literal

from pydantic import Field

from commerce.schemas import StrictModel

Alias = Literal["self", "dad", "mom", "sister"]


class FamilyIntent(StrictModel):
    members: list[Alias] = Field(max_length=4)
    max_amount_minor: int | None = Field(default=None, gt=0, le=100000)
    budget_comparison: Literal["lt", "lte"] = "lte"
    currency: str = Field(default="USD", pattern="^[A-Z]{3}$")
    location: Literal["nearest_home", "unspecified"] = "nearest_home"
    clarification: str | None = Field(default=None, max_length=300)


class PickupInput(StrictModel):
    text: str = Field(min_length=3, max_length=2000)
    channel: Literal["text", "voice"] = "text"


class PermissionInput(StrictModel):
    members: list[Alias] = Field(min_length=1, max_length=4)
    per_order_minor: int = Field(gt=0, le=100000)
    total_minor: int = Field(gt=0, le=300000)
    max_orders: int = Field(default=3, ge=1, le=20)
    valid_for_seconds: int = Field(default=86400, ge=60, le=86400)


class StaffAction(StrictModel):
    action: Literal["ready", "reject", "collect"]
    clinical_review_confirmed: bool = False
    pickup_code: str | None = Field(default=None, max_length=12)


class ScenarioInput(StrictModel):
    scenario: Literal[
        "normal",
        "coverage_pending",
        "access_revoked",
        "no_refills",
        "out_of_stock",
        "payment_response_lost",
    ]
