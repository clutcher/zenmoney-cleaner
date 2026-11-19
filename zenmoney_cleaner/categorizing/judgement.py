from dataclasses import dataclass

from zenmoney_cleaner.settings.settings import Confidence
from zenmoney_cleaner.snapshot.snapshot import Account, Category


@dataclass(frozen=True)
class Recategorize:
    category: Category
    confidence: Confidence
    reason: str
    source: str


@dataclass(frozen=True)
class Delete:
    reason: str
    source: str


@dataclass(frozen=True)
class ConvertToTransfer:
    to_account: Account
    reason: str
    source: str


@dataclass(frozen=True)
class Undecided:
    reason: str
    likely_category_name: str | None = None


Change = Recategorize | Delete | ConvertToTransfer
Judgement = Change | Undecided
