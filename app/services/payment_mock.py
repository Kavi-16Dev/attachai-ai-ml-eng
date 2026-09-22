from dataclasses import dataclass

from app.config import settings


class PaymentTimeoutError(Exception):
    """Raised when the (mock) payment provider times out with an ambiguous
    response — the caller does not know whether the charge went through."""


@dataclass
class ChargeResult:
    status: str  # "succeeded" | "failed"


class PaymentMockClient:
    def __init__(self) -> None:
        # Every attempted charge, in order — a stand-in for the provider's own
        # ledger, useful for proving a bug caused two real-world charges.
        self.charge_log: list[int] = []

    def charge(self, amount_cents: int) -> ChargeResult:
        self.charge_log.append(amount_cents)
        if amount_cents == settings.payment_timeout_trigger_cents:
            raise PaymentTimeoutError("provider timed out")
        if amount_cents <= 0:
            return ChargeResult(status="failed")
        return ChargeResult(status="succeeded")


payment_mock_client = PaymentMockClient()
