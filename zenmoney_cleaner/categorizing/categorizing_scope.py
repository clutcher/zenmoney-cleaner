from dataclasses import dataclass
from datetime import date
from enum import Enum

from zenmoney_cleaner.snapshot.transaction import Transaction, TransactionKind


class CategorizingMode(Enum):
    WITHOUT_CATEGORY = "without-category"
    NEW_IN_ZENMONEY = "new-in-zenmoney"
    RECHECK_ALL = "recheck-all"
    SINCE_LAST_CHECK = "since-last-check"

    def takes(self, transaction: Transaction) -> bool:
        if self == CategorizingMode.WITHOUT_CATEGORY:
            return not transaction.has_category()
        if self == CategorizingMode.NEW_IN_ZENMONEY:
            return not transaction.is_reviewed
        return True


@dataclass(frozen=True)
class CategorizingScope:
    mode: CategorizingMode
    from_date: date | None = None
    to_date: date | None = None
    account_names: frozenset[str] = frozenset()
    kind: TransactionKind | None = None

    def covers(self, transaction: Transaction) -> bool:
        if not self.mode.takes(transaction):
            return False
        if self.from_date is not None and transaction.date < self.from_date:
            return False
        if self.to_date is not None and transaction.date > self.to_date:
            return False
        if self.account_names and transaction.account_name not in self.account_names:
            return False
        if self.kind is not None and transaction.kind != self.kind:
            return False
        return True
