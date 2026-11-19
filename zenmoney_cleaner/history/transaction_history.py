from dataclasses import dataclass, replace
from datetime import date, timedelta

from zenmoney_cleaner.snapshot.currency import Currency
from zenmoney_cleaner.snapshot.snapshot import Account, Snapshot
from zenmoney_cleaner.snapshot.transaction import Transaction, TransactionKind

_KEPT_DAYS = 396
_FIRST_RUN_DAYS = 92


@dataclass(frozen=True)
class HistoryEntry:
    id: str
    date: date
    kind: TransactionKind
    account_id: str
    payee: str
    amount: float
    category_id: str | None


@dataclass(frozen=True)
class FetchRange:
    from_date: date
    to_date: date
    is_first_run: bool


@dataclass(frozen=True)
class TransactionHistory:
    entries: tuple[HistoryEntry, ...]
    last_check: date | None

    @classmethod
    def empty(cls) -> "TransactionHistory":
        return cls((), None)

    def plan_fetch(self, today: date, overlap_days: int) -> FetchRange:
        if not self.entries:
            return FetchRange(today - timedelta(days=_FIRST_RUN_DAYS), today, True)

        newest_day = max(entry.date for entry in self.entries)
        return FetchRange(min(newest_day, today) - timedelta(days=overlap_days), today, False)

    def replace_range(self, fresh_transactions: tuple[Transaction, ...], from_date: date, to_date: date) -> "TransactionHistory":
        fresh_ids = {transaction.id for transaction in fresh_transactions}
        kept_entries = [
            entry for entry in self.entries if entry.id not in fresh_ids and not from_date <= entry.date <= to_date
        ]
        fresh_entries = [_make_entry(transaction) for transaction in fresh_transactions if transaction.is_categorizable()]
        entries = sorted([*kept_entries, *fresh_entries], key=lambda entry: (entry.date, entry.id))
        if not entries:
            return replace(self, entries=())

        oldest_kept_day = entries[-1].date - timedelta(days=_KEPT_DAYS)
        return replace(self, entries=tuple(entry for entry in entries if entry.date >= oldest_kept_day))

    def record_check(self, checked_until: date) -> "TransactionHistory":
        if self.last_check is not None and self.last_check >= checked_until:
            return self

        return replace(self, last_check=checked_until)

    def list_transactions(self, snapshot: Snapshot) -> tuple[Transaction, ...]:
        snapshot_ids = {transaction.id for transaction in snapshot.transactions}
        accounts_by_id_map = {account.id: account for account in snapshot.accounts}
        category_names_by_id_map = {category.id: category.full_name for category in snapshot.categories}
        return tuple(
            _make_transaction(entry, accounts_by_id_map[entry.account_id], category_names_by_id_map.get(entry.category_id))
            for entry in self.entries
            if entry.id not in snapshot_ids and entry.account_id in accounts_by_id_map
        )


def _make_entry(transaction: Transaction) -> HistoryEntry:
    return HistoryEntry(
        id=transaction.id,
        date=transaction.date,
        kind=transaction.kind,
        account_id=transaction.account_id,
        payee=transaction.payee,
        amount=transaction.amount,
        category_id=transaction.category_id,
    )


def _make_transaction(entry: HistoryEntry, account: Account, category_name: str | None) -> Transaction:
    return Transaction(
        id=entry.id,
        date=entry.date,
        kind=entry.kind,
        account_id=entry.account_id,
        account_name=account.name,
        amount=entry.amount,
        currency=Currency(account.instrument),
        category_id=entry.category_id if category_name is not None else None,
        category_name=category_name,
        payee=entry.payee,
        comment="",
        is_balance_adjustment=False,
    )
