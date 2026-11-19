import json
from datetime import date
from pathlib import Path
from typing import Any

from zenmoney_cleaner.snapshot.snapshot import Account, Category, Snapshot
from zenmoney_cleaner.snapshot.transaction import Transaction, TransactionKind


def write_snapshot(snapshot: Snapshot, path: Path) -> None:
    raw_snapshot = {
        "balanceAdjustmentCategoryId": snapshot.balance_adjustment_category_id,
        "categories": [vars(category) for category in snapshot.categories],
        "accounts": [vars(account) for account in snapshot.accounts],
        "transactions": [_write_transaction(transaction) for transaction in snapshot.transactions],
    }
    path.write_text(json.dumps(raw_snapshot, ensure_ascii=False, indent=1), encoding="utf-8")


def read_snapshot(path: Path) -> Snapshot:
    raw_snapshot = json.loads(path.read_text(encoding="utf-8"))
    return Snapshot(
        transactions=tuple(_read_transaction(raw) for raw in raw_snapshot["transactions"]),
        categories=tuple(Category(**raw) for raw in raw_snapshot["categories"]),
        accounts=tuple(Account(**raw) for raw in raw_snapshot["accounts"]),
        balance_adjustment_category_id=raw_snapshot["balanceAdjustmentCategoryId"],
    )


def _write_transaction(transaction: Transaction) -> dict[str, Any]:
    return vars(transaction) | {"date": transaction.date.isoformat(), "kind": transaction.kind.value}


def _read_transaction(raw: dict[str, Any]) -> Transaction:
    return Transaction(**(raw | {"date": date.fromisoformat(raw["date"]), "kind": TransactionKind(raw["kind"])}))
