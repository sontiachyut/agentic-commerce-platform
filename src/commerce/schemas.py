from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Actor(StrictModel):
    user_id: str
    tenant_id: str = "demo"
    role: Literal["shopper", "operator"] = "shopper"


class LoginRequest(StrictModel):
    persona: Literal["alex", "sam", "operator"] = "alex"


class SessionRequest(StrictModel):
    request: str = Field(min_length=3, max_length=2000)
    grant_id: str | None = None


class ApprovalRequest(StrictModel):
    quote_digest: str = Field(min_length=64, max_length=64)


class ExecutionRequest(StrictModel):
    quote_id: str
    approval_id: str | None = None
    grant_id: str | None = None
    grant_version: int | None = None
    fault_profile: Literal[
        "none",
        "payment_response_lost",
        "dispense_response_lost",
        "capture_response_lost",
        "payment_declined",
        "dispense_failed",
        "capture_declined",
        "captured_dispense_failed",
        "compensation_response_lost",
        "source_unavailable",
    ] = "none"


class GrantRequest(StrictModel):
    product_ids: list[str] = Field(min_length=1, max_length=20)
    kiosk_ids: list[str] = Field(default=["kiosk-a"], min_length=1, max_length=10)
    per_purchase_minor: int = Field(gt=0, le=100_000)
    total_minor: int = Field(gt=0, le=1_000_000)
    max_purchases: int = Field(default=1, ge=1, le=100)
    valid_for_seconds: int = Field(default=3600, ge=1, le=86400)


class PriceUpdate(StrictModel):
    price_minor: int = Field(gt=0, le=100_000)


class Intent(StrictModel):
    query: str = Field(default="", max_length=160)
    category: Literal["protein-bar", "snack", "drink", "any"] = "any"
    kiosk_id: str = Field(default="kiosk-a", max_length=64)
    max_amount_minor: int | None = Field(default=None, gt=0, le=1_000_000)
    quantity: int = Field(default=1, ge=1, le=1)
    clarification: str | None = Field(default=None, max_length=300)

    @field_validator("kiosk_id", mode="before")
    @classmethod
    def normalize_kiosk(cls, value):
        if isinstance(value, str):
            return "-".join(value.strip().lower().replace("_", " ").replace("-", " ").split())
        return value


class Selection(StrictModel):
    product_id: str | None
    reason: str = Field(max_length=500)
    clarification: str | None = Field(default=None, max_length=300)
