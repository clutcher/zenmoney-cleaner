import json
from datetime import date
from pathlib import Path

from zenmoney_cleaner.categorizing.categorizing_scope import CategorizingMode, CategorizingScope
from zenmoney_cleaner.snapshot.transaction import TransactionKind

_SCOPE_FILE_NAME = "scope.json"


class MissingScopeError(Exception):
    pass


def write_scope(scope: CategorizingScope, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    raw_scope = {
        "mode": scope.mode.value,
        "from": scope.from_date.isoformat() if scope.from_date else None,
        "to": scope.to_date.isoformat() if scope.to_date else None,
        "accounts": sorted(scope.account_names),
        "type": scope.kind.value if scope.kind else None,
    }
    (directory / _SCOPE_FILE_NAME).write_text(json.dumps(raw_scope, ensure_ascii=False, indent=1), encoding="utf-8")


def read_scope(directory: Path) -> CategorizingScope:
    path = directory / _SCOPE_FILE_NAME
    if not path.exists():
        raise MissingScopeError(f"{path} is missing; run prepare first")

    raw_scope = json.loads(path.read_text(encoding="utf-8"))
    return CategorizingScope(
        mode=CategorizingMode(raw_scope["mode"]),
        from_date=date.fromisoformat(raw_scope["from"]) if raw_scope.get("from") else None,
        to_date=date.fromisoformat(raw_scope["to"]) if raw_scope.get("to") else None,
        account_names=frozenset(raw_scope.get("accounts") or []),
        kind=TransactionKind(raw_scope["type"]) if raw_scope.get("type") else None,
    )
