import json
from datetime import date
from pathlib import Path
from typing import Any

from zenmoney_cleaner.history.transaction_history import HistoryEntry, TransactionHistory
from zenmoney_cleaner.snapshot.transaction import TransactionKind


def read_history(path: Path) -> TransactionHistory:
    if not path.exists():
        return TransactionHistory.empty()

    raw_history = json.loads(path.read_text(encoding="utf-8"))
    return TransactionHistory(
        entries=tuple(_read_entry(raw_entry) for raw_entry in raw_history.get("transactions", [])),
        last_check=date.fromisoformat(raw_history["lastCheck"]) if raw_history.get("lastCheck") else None,
    )


def write_history(history: TransactionHistory, path: Path) -> None:
    raw_history = {
        "lastCheck": history.last_check.isoformat() if history.last_check else None,
        "transactions": [_write_entry(entry) for entry in history.entries],
    }
    path.write_text(json.dumps(raw_history, ensure_ascii=False, indent=1), encoding="utf-8")


def _read_entry(raw_entry: dict[str, Any]) -> HistoryEntry:
    return HistoryEntry(
        id=raw_entry["id"],
        date=date.fromisoformat(raw_entry["date"]),
        kind=TransactionKind(raw_entry["kind"]),
        account_id=raw_entry["accountId"],
        payee=raw_entry["payee"],
        amount=raw_entry["amount"],
        category_id=raw_entry.get("categoryId"),
    )


def _write_entry(entry: HistoryEntry) -> dict[str, Any]:
    return {
        "id": entry.id,
        "date": entry.date.isoformat(),
        "kind": entry.kind.value,
        "accountId": entry.account_id,
        "payee": entry.payee,
        "amount": entry.amount,
        "categoryId": entry.category_id,
    }
