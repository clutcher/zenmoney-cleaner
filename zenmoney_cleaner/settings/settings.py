import re
from dataclasses import dataclass
from enum import Enum

from zenmoney_cleaner.snapshot.transaction import Transaction, TransactionKind


class Confidence(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    def reaches(self, minimum: "Confidence") -> bool:
        return _CONFIDENCE_ORDER.index(self) <= _CONFIDENCE_ORDER.index(minimum)


_CONFIDENCE_ORDER = [Confidence.HIGH, Confidence.MEDIUM, Confidence.LOW]


@dataclass(frozen=True)
class Location:
    country: str
    country_code: str
    city: str | None = None


@dataclass(frozen=True)
class RuleCondition:
    payees: frozenset[str] = frozenset()
    comment_fragments: tuple[str, ...] = ()
    account_name: str | None = None
    kind: TransactionKind | None = None

    def holds(self, transaction: Transaction, merchant_key: str | None) -> bool:
        if self.payees and (merchant_key or "").lower() not in self.payees:
            return False
        if self.comment_fragments and not any(fragment in transaction.comment.lower() for fragment in self.comment_fragments):
            return False
        if self.account_name is not None and transaction.account_name != self.account_name:
            return False
        if self.kind is not None and transaction.kind != self.kind:
            return False
        return True


@dataclass(frozen=True)
class CategorizeAction:
    category_key: str
    reason: str


@dataclass(frozen=True)
class DeleteAction:
    reason: str


@dataclass(frozen=True)
class TransferAction:
    to_account_name: str
    reason: str


RuleAction = CategorizeAction | DeleteAction | TransferAction


@dataclass(frozen=True)
class Rule:
    name: str
    condition: RuleCondition
    action: RuleAction


@dataclass(frozen=True)
class CorrectionSettings:
    match_window_days: int
    max_match_size: int
    adjustment_category_name: str | None = None


@dataclass(frozen=True)
class HistorySettings:
    overlap_days: int


@dataclass(frozen=True)
class Settings:
    location: Location
    category_names_by_key_map: dict[str, str]
    payee_strip_patterns: tuple[re.Pattern[str], ...]
    rules: tuple[Rule, ...]
    corrections: CorrectionSettings
    history: HistorySettings

    def find_rule(self, transaction: Transaction, merchant_key: str | None) -> Rule | None:
        return next((rule for rule in self.rules if rule.condition.holds(transaction, merchant_key)), None)
