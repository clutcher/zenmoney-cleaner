from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any

from zenmoney_cleaner.settings.settings import Confidence

_BATCH_SIZE = 200
_NEW_MODE = "new-in-zenmoney"
_COMMENT_SEPARATOR = " · "


class ProposalFormatError(Exception):
    pass


@dataclass(frozen=True)
class Confirmation:
    transaction_id: str
    category_id: str
    category_name: str
    confirmed_by: str
    reason: str
    payee: str
    day: str
    amount: float
    comment: str | None = None


@dataclass(frozen=True)
class ReviewAnswers:
    minimum_confidence: Confidence
    skipped_merchant_keys: frozenset[str] = frozenset()
    kept_merchant_keys: frozenset[str] = frozenset()
    chosen_category_keys_by_merchant_key_map: dict[str, str] = field(default_factory=dict)
    kept_undecided_merchant_keys: frozenset[str | None] = frozenset()
    comments_by_merchant_key_map: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Approval:
    upsert_batches: tuple[tuple[dict[str, Any], ...], ...]
    delete_batches: tuple[tuple[str, ...], ...]
    confirmations: tuple[Confirmation, ...]
    checked_until: date | None = None


def approve_proposal(raw_proposal: dict[str, Any], answers: ReviewAnswers) -> Approval:
    changes = _read_changes(raw_proposal)
    undecided = raw_proposal.get("undecided", [])
    user_decided_merchant_keys = answers.skipped_merchant_keys | answers.kept_merchant_keys | set(answers.chosen_category_keys_by_merchant_key_map)
    approved_changes = [
        change
        for change in changes
        if Confidence(change["confidence"]).reaches(answers.minimum_confidence) and change["merchantKey"] not in user_decided_merchant_keys
    ]
    open_items = changes + undecided
    kept_items = [
        item
        for item in changes + undecided
        if item["transaction"]["currentCategoryId"]
        and (item["merchantKey"] in answers.kept_merchant_keys or (item in undecided and item["merchantKey"] in answers.kept_undecided_merchant_keys))
    ]
    chosen_items = [item for item in open_items if item["merchantKey"] in answers.chosen_category_keys_by_merchant_key_map]
    agreements = [agreement for agreement in raw_proposal.get("agreements", []) if agreement["merchantKey"] not in answers.skipped_merchant_keys]

    unchanged_confirmations = [_confirm_current_category(item, "user", "user kept the current category") for item in kept_items] + [
        _confirm_current_category(agreement, agreement["source"], agreement.get("reason", "")) for agreement in agreements
    ]
    chosen_confirmations = [
        _confirm_chosen_category(item, _find_chosen_category(raw_proposal, answers.chosen_category_keys_by_merchant_key_map[item["merchantKey"]]))
        for item in chosen_items
    ]
    confirmations = (
        [_confirm_new_category(change) for change in approved_changes if change["action"] == "categorize"]
        + chosen_confirmations
        + unchanged_confirmations
    )

    upserts = [change["upsert"] for change in approved_changes if change.get("upsert")]
    upserts += [{"id": confirmation.transaction_id, "categoryId": confirmation.category_id} for confirmation in chosen_confirmations]
    if raw_proposal.get("mode") == _NEW_MODE:
        upserts += [{"id": confirmation.transaction_id, "isReviewed": True} for confirmation in unchanged_confirmations]
    delete_ids = [change["deleteId"] for change in approved_changes if change.get("deleteId")]

    decided_items = [change for change in approved_changes if not change.get("deleteId")] + kept_items + chosen_items + agreements
    comments_by_transaction_id_map = _join_comments(decided_items, answers.comments_by_merchant_key_map)
    confirmations = [replace(confirmation, comment=comments_by_transaction_id_map.get(confirmation.transaction_id)) for confirmation in confirmations]
    upserts = _add_comments(upserts, comments_by_transaction_id_map)

    decided_ids = {change["transaction"]["id"] for change in approved_changes} | {
        confirmation.transaction_id for confirmation in confirmations
    }
    return Approval(_split(upserts), _split(delete_ids), tuple(confirmations), _find_checked_until(raw_proposal, open_items, decided_ids))


def _find_checked_until(raw_proposal: dict[str, Any], open_items: list[dict[str, Any]], decided_ids: set[str]) -> date | None:
    if not raw_proposal.get("checkedUntil"):
        return None

    left_open_days = [date.fromisoformat(item["transaction"]["date"]) for item in open_items if item["transaction"]["id"] not in decided_ids]
    return min(left_open_days, default=date.fromisoformat(raw_proposal["checkedUntil"]))


def _join_comments(decided_items: list[dict[str, Any]], comments_by_merchant_key_map: dict[str, str]) -> dict[str, str]:
    unknown_merchant_keys = set(comments_by_merchant_key_map) - {item["merchantKey"] for item in decided_items}
    if unknown_merchant_keys:
        raise ProposalFormatError(f"--comment names merchant keys that no approved, kept or set row holds: {sorted(unknown_merchant_keys)}")

    return {
        item["transaction"]["id"]: _join_comment(item["transaction"]["comment"], comments_by_merchant_key_map[item["merchantKey"]])
        for item in decided_items
        if item["merchantKey"] in comments_by_merchant_key_map
    }


def _join_comment(current_comment: str, added_text: str) -> str:
    if not current_comment:
        return added_text
    if added_text in current_comment:
        return current_comment

    return f"{current_comment}{_COMMENT_SEPARATOR}{added_text}"


def _add_comments(upserts: list[dict[str, Any]], comments_by_transaction_id_map: dict[str, str]) -> list[dict[str, Any]]:
    commented_upserts: list[dict[str, Any]] = []
    commented_ids: set[str] = set()
    for upsert in upserts:
        if upsert["id"] in comments_by_transaction_id_map and upsert["id"] not in commented_ids:
            upsert = upsert | {"comment": comments_by_transaction_id_map[upsert["id"]]}
            commented_ids.add(upsert["id"])
        commented_upserts.append(upsert)

    return commented_upserts + [
        {"id": transaction_id, "comment": comment}
        for transaction_id, comment in comments_by_transaction_id_map.items()
        if transaction_id not in commented_ids
    ]


def _read_changes(raw_proposal: dict[str, Any]) -> list[dict[str, Any]]:
    changes = raw_proposal.get("changes")
    if not isinstance(changes, list):
        raise ProposalFormatError("the proposal has no list of changes")

    for index, change in enumerate(changes):
        if change.get("confidence") not in {confidence.value for confidence in Confidence}:
            raise ProposalFormatError(f"change {index} has no valid confidence")
        if not change.get("upsert") and not change.get("deleteId"):
            raise ProposalFormatError(f"change {index} holds neither an upsert nor a deleteId")
    return changes


def _confirm_new_category(change: dict[str, Any]) -> Confirmation:
    transaction = change["transaction"]
    return Confirmation(
        transaction_id=transaction["id"],
        category_id=change["upsert"]["categoryId"],
        category_name=change["newCategory"],
        confirmed_by=f"user approved {change['source']}",
        reason=change.get("reason", ""),
        payee=transaction["payee"],
        day=transaction["date"],
        amount=transaction["amount"],
    )


def _find_chosen_category(raw_proposal: dict[str, Any], category_key: str) -> dict[str, Any]:
    category = raw_proposal.get("categoriesByKey", {}).get(category_key)
    if category is None:
        raise ProposalFormatError(f"the category key {category_key!r} of --set is not a key of config.yml")
    return category


def _confirm_chosen_category(raw_item: dict[str, Any], category: dict[str, Any]) -> Confirmation:
    transaction = raw_item["transaction"]
    return Confirmation(
        transaction_id=transaction["id"],
        category_id=category["id"],
        category_name=category["name"],
        confirmed_by="user",
        reason="user chose the category",
        payee=transaction["payee"],
        day=transaction["date"],
        amount=transaction["amount"],
    )


def _confirm_current_category(raw_item: dict[str, Any], confirmed_by: str, reason: str) -> Confirmation:
    transaction = raw_item["transaction"]
    return Confirmation(
        transaction_id=transaction["id"],
        category_id=transaction["currentCategoryId"],
        category_name=transaction["currentCategory"],
        confirmed_by=confirmed_by,
        reason=reason,
        payee=transaction["payee"],
        day=transaction["date"],
        amount=transaction["amount"],
    )


def _split(items: list[Any]) -> tuple[tuple[Any, ...], ...]:
    return tuple(tuple(items[start : start + _BATCH_SIZE]) for start in range(0, len(items), _BATCH_SIZE))
