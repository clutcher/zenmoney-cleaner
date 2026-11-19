from dataclasses import dataclass
from datetime import date
from enum import Enum


class TransactionKind(Enum):
    EXPENSE = "expense"
    INCOME = "income"
    TRANSFER = "transfer"


@dataclass(frozen=True)
class Transaction:
    id: str
    date: date
    kind: TransactionKind
    account_id: str
    account_name: str
    amount: float
    category_id: str | None
    category_name: str | None
    payee: str
    comment: str
    is_balance_adjustment: bool
    is_reviewed: bool = True
    is_synced: bool = False

    def has_category(self) -> bool:
        return self.category_id is not None

    def is_categorizable(self) -> bool:
        return self.kind != TransactionKind.TRANSFER and not self.is_balance_adjustment

    def is_auto_correction(self) -> bool:
        return self.is_balance_adjustment and self.is_synced_without_payee()

    def is_synced_without_payee(self) -> bool:
        return self.is_synced and not self.payee

    def signed_amount(self) -> float:
        return -self.amount if self.kind == TransactionKind.EXPENSE else self.amount
