import hashlib
import json


class DomainError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


def digest(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def canonical_terms(quote) -> dict:
    return {
        key: getattr(quote, key)
        for key in (
            "id",
            "tenant_id",
            "user_id",
            "session_id",
            "product_id",
            "kiosk_id",
            "quantity",
            "price_version",
            "amount_minor",
            "currency",
            "expires_at",
        )
    }


def outcome(execution) -> dict:
    success = (
        execution.state == "COMPLETED"
        and execution.payment_state == "CAPTURED"
        and execution.fulfillment_state == "DISPENSED"
    )
    if success:
        text = "Purchase complete. Payment captured and item delivery confirmed."
    elif execution.state == "CANCELED":
        text = (
            "Purchase not completed. Payment was declined or its cancellation/refund is confirmed."
        )
    elif execution.state == "RECOVERY_REQUIRED":
        text = "This purchase needs review. The recorded payment and delivery states are shown below. No second item will be delivered."
    else:
        text = "Purchase is pending. We are checking the original transaction before taking another action."
    return {
        "success": success,
        "message": text,
        "order_state": execution.state,
        "payment_state": execution.payment_state,
        "fulfillment_state": execution.fulfillment_state,
        "compensation_state": execution.compensation_state,
        "source_version": execution.version,
    }
