from datetime import date
from pathlib import Path
from typing import Any

import yaml

from zenmoney_cleaner.applying.approval import Confirmation
from zenmoney_cleaner.categorizing.verified_transactions import VerifiedEntry, VerifiedTransactions


def read_verified_transactions(path: Path) -> VerifiedTransactions:
    raw_entries = _read_entries(path)
    return VerifiedTransactions({
        transaction_id: VerifiedEntry(
            transaction_id=transaction_id,
            category_id=str(raw_entry["category_id"]),
            category_name=str(raw_entry.get("category", "")),
            payee=str(raw_entry.get("payee") or ""),
            reason=str(raw_entry.get("reason") or raw_entry.get("by") or ""),
            confirmed_on=str(raw_entry.get("confirmed", "")),
        )
        for transaction_id, raw_entry in raw_entries.items()
    })


def record_confirmations(path: Path, confirmations: tuple[Confirmation, ...], confirmed_on: date) -> None:
    raw_entries = _read_entries(path)
    for confirmation in confirmations:
        raw_entries[confirmation.transaction_id] = {
            "category": confirmation.category_name,
            "category_id": confirmation.category_id,
            "by": confirmation.confirmed_by,
            "reason": confirmation.reason,
            "confirmed": confirmed_on.isoformat(),
            "date": confirmation.day,
            "amount": confirmation.amount,
            "payee": confirmation.payee,
        }

    path.write_text(yaml.safe_dump(raw_entries, allow_unicode=True, sort_keys=True), encoding="utf-8")


def _read_entries(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}

    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
