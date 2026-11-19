import json
from collections import Counter
from pathlib import Path
from typing import Any

from zenmoney_cleaner.categorizing.category_catalog import CategoryCatalog
from zenmoney_cleaner.categorizing.category_proposal import Agreement, CategoryProposal, ProposedChange, UnknownMerchant
from zenmoney_cleaner.categorizing.judgement import ConvertToTransfer, Delete, Recategorize
from zenmoney_cleaner.settings.settings import Confidence
from zenmoney_cleaner.snapshot.transaction import Transaction, TransactionKind

_NO_PAYEE_TEXT = "(no payee)"
_EXAMPLE_COUNT = 3
_ROW_HEADER = "| # | Date | Shop | Account | Amount | Comment | Now → New | Why |"
_ROW_RULE = "|---|---|---|---|---|---|---|---|"


def write_category_proposal(proposal: CategoryProposal, catalog: CategoryCatalog, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    raw_changes = [_write_change(proposed_change) for proposed_change in proposal.changes]
    raw_agreements = [_write_agreement(agreement) for agreement in proposal.agreements]
    raw_undecided = [
        {"merchantKey": merchant.merchant_key, "transaction": write_transaction_line(transaction)}
        for merchant in proposal.unknown_merchants
        for transaction in merchant.transactions
    ]
    raw_unknown_merchants = [_write_unknown_merchant(merchant) for merchant in proposal.unknown_merchants]
    raw_unknown_merchants.sort(key=lambda merchant: -merchant["transactionCount"])

    raw_proposal = {
        "mode": proposal.scope.mode.value,
        "changes": raw_changes,
        "agreements": raw_agreements,
        "undecided": raw_undecided,
        "categoriesByKey": {key: vars(catalog.get_category(key)) for key in catalog.list_keys()},
    }
    _write_json(raw_proposal, directory / "proposal.json")
    _write_json(raw_unknown_merchants, directory / "unknown-merchants.json")
    proposal_text = _render_markdown(proposal.scope.mode.value, raw_changes, raw_agreements, raw_unknown_merchants, raw_undecided)
    (directory / "proposal.md").write_text(proposal_text, encoding="utf-8")


def _write_change(proposed_change: ProposedChange) -> dict[str, Any]:
    transaction = proposed_change.transaction
    change = proposed_change.change
    raw_change = {
        "merchantKey": proposed_change.merchant_key,
        "transaction": write_transaction_line(transaction),
        "reason": change.reason,
        "source": change.source,
    }
    if isinstance(change, Recategorize):
        return raw_change | {
            "action": "categorize",
            "newCategory": change.category.full_name,
            "confidence": change.confidence.value,
            "upsert": {"id": transaction.id, "categoryId": change.category.id},
        }
    if isinstance(change, Delete):
        return raw_change | {"action": "delete", "confidence": Confidence.HIGH.value, "deleteId": transaction.id}

    return raw_change | {
        "action": "transfer",
        "toAccount": change.to_account.name,
        "confidence": Confidence.HIGH.value,
        "upsert": _build_transfer_upsert(transaction, change),
    }


def _write_agreement(agreement: Agreement) -> dict[str, Any]:
    return {
        "merchantKey": agreement.merchant_key,
        "transaction": write_transaction_line(agreement.transaction),
        "reason": agreement.evidence.reason,
        "source": agreement.evidence.source,
        "confidence": agreement.evidence.confidence.value,
    }


def _build_transfer_upsert(transaction: Transaction, change: ConvertToTransfer) -> dict[str, Any]:
    own_side = {"accountId": transaction.account_id, "amount": transaction.amount}
    other_side = {"accountId": change.to_account.id, "amount": transaction.amount}
    if transaction.kind == TransactionKind.INCOME:
        return {"id": transaction.id, "expense": other_side, "income": own_side}
    return {"id": transaction.id, "expense": own_side, "income": other_side}


def write_transaction_line(transaction: Transaction) -> dict[str, Any]:
    return {
        "id": transaction.id,
        "date": transaction.date.isoformat(),
        "account": transaction.account_name,
        "amount": transaction.signed_amount(),
        "payee": transaction.payee,
        "comment": transaction.comment,
        "currentCategory": transaction.category_name,
        "currentCategoryId": transaction.category_id,
    }


def _write_unknown_merchant(merchant: UnknownMerchant) -> dict[str, Any]:
    current_category_counts = Counter(transaction.category_name or "(none)" for transaction in merchant.transactions)
    return {
        "merchantKey": merchant.merchant_key,
        "payees": sorted({transaction.payee for transaction in merchant.transactions}),
        "transactionCount": len(merchant.transactions),
        "totalAmount": round(sum(transaction.signed_amount() for transaction in merchant.transactions), 2),
        "currentCategories": dict(current_category_counts),
        "reasons": list(merchant.reasons),
        "examples": [write_transaction_line(transaction) for transaction in merchant.transactions[:_EXAMPLE_COUNT]],
    }


def _render_markdown(
    mode: str,
    raw_changes: list[dict[str, Any]],
    raw_agreements: list[dict[str, Any]],
    raw_unknown_merchants: list[dict[str, Any]],
    raw_undecided: list[dict[str, Any]],
) -> str:
    summary_text = (
        f"{len(raw_changes)} changes, {len(raw_agreements)} transactions confirmed, "
        f"{len(raw_unknown_merchants)} merchants undecided. The numbers run on from Changes into Undecided, so each number names 1 row."
    )
    lines = [f"# Category proposal ({mode})", "", summary_text, ""]

    change_groups = _group_by_merchant(raw_changes)
    lines += ["## Changes", "", _ROW_HEADER, _ROW_RULE]
    for number, (merchant_key, merchant_changes) in enumerate(change_groups, start=1):
        first_change = merchant_changes[0]
        target_text = f"{first_change['transaction']['currentCategory'] or '(none)'} → {_describe_target(first_change)}"
        why_text = f"{first_change['confidence']}, {first_change['source']}: {first_change['reason']}"
        lines.append(_render_row(number, merchant_key, [change["transaction"] for change in merchant_changes], target_text, why_text))
    lines.append("")

    lines += ["## Undecided", "", _ROW_HEADER, _ROW_RULE]
    for number, merchant in enumerate(raw_unknown_merchants, start=len(change_groups) + 1):
        transactions = [item["transaction"] for item in raw_undecided if item["merchantKey"] == merchant["merchantKey"]]
        current_categories_text = ", ".join(merchant["currentCategories"])
        lines.append(_render_row(number, merchant["merchantKey"], transactions, f"{current_categories_text} → ?", "; ".join(merchant["reasons"])))
    lines.append("")

    lines += ["## Confirmed", "", "| Merchant | Category | Transactions | Evidence |", "|---|---|---|---|"]
    for merchant_key, merchant_agreements in _group_agreements(raw_agreements):
        first_agreement = merchant_agreements[0]
        evidence_text = f"{first_agreement['source']}: {first_agreement['reason']}".replace("|", "/")
        lines.append(
            f"| {merchant_key or _NO_PAYEE_TEXT} | {first_agreement['transaction']['currentCategory']} | {len(merchant_agreements)} | {evidence_text} |"
        )
    return "\n".join(lines) + "\n"


def _render_row(number: int, merchant_key: str | None, transactions: list[dict[str, Any]], target_text: str, why_text: str) -> str:
    dates = sorted(transaction["date"] for transaction in transactions)
    date_text = dates[0] if len(dates) == 1 else f"{dates[0]} … {dates[-1]} (×{len(dates)})"
    account_text = ", ".join(dict.fromkeys(transaction["account"] for transaction in transactions))
    amount_text = str(round(sum(transaction["amount"] for transaction in transactions), 2))
    comment_text = next((transaction["comment"] for transaction in transactions if transaction["comment"]), "")
    cells = [str(number), date_text, merchant_key or _NO_PAYEE_TEXT, account_text, amount_text, comment_text, target_text, why_text]
    return "| " + " | ".join(cell.replace("|", "/") for cell in cells) + " |"


def _group_by_merchant(raw_changes: list[dict[str, Any]]) -> list[tuple[str | None, list[dict[str, Any]]]]:
    changes_by_group_map: dict[tuple[str | None, str], list[dict[str, Any]]] = {}
    for change in raw_changes:
        changes_by_group_map.setdefault((change["merchantKey"], _describe_target(change)), []).append(change)

    groups = sorted(changes_by_group_map.items(), key=lambda group: -len(group[1]))
    return [(merchant_key, changes) for (merchant_key, _), changes in groups]


def _group_agreements(raw_agreements: list[dict[str, Any]]) -> list[tuple[str | None, list[dict[str, Any]]]]:
    agreements_by_group_map: dict[tuple[str | None, str], list[dict[str, Any]]] = {}
    for agreement in raw_agreements:
        group_key = (agreement["merchantKey"], agreement["transaction"]["currentCategory"])
        agreements_by_group_map.setdefault(group_key, []).append(agreement)

    groups = sorted(agreements_by_group_map.items(), key=lambda group: -len(group[1]))
    return [(merchant_key, agreements) for (merchant_key, _), agreements in groups]


def _describe_target(raw_change: dict[str, Any]) -> str:
    if raw_change["action"] == "categorize":
        return raw_change["newCategory"]
    if raw_change["action"] == "delete":
        return "delete"
    return f"transfer to {raw_change['toAccount']}"


def _write_json(raw: Any, path: Path) -> None:
    path.write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")
