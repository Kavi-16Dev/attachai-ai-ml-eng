from pydantic import BaseModel


class ConfirmPaymentIn(BaseModel):
    amount_cents: int
