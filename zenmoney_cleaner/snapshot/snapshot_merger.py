from datetime import date
from typing import Any

from zenmoney_cleaner.snapshot.snapshot import Account, Category, Snapshot
from zenmoney_cleaner.snapshot.transaction import Transaction, TransactionKind

RawObject = dict[str, Any]


class IncompletePagesError(Exception):
    pass


class UnknownAccountError(Exception):
    pass


def merge_snapshot(pages_by_query: list[list[RawObject]], categories_response: RawObject, accounts_response: RawObject) -> Snapshot:
    for query_pages in pages_by_query:
        _check_pages_complete(query_pages)
    pages = [page for query_pages in pages_by_query for page in query_pages]

    categories = read_categories(categories_response["data"])
    accounts = tuple(_read_account(raw_account) for raw_account in accounts_response["data"])
    balance_adjustment_category_id = categories_response.get("balanceAdjustmentCategoryId")
    merchant_names_by_id_map = _collect_merchant_names(pages)
    raw_transactions_by_id_map = {raw["id"]: raw for page in pages for raw in page["data"]}

    transactions = tuple(_read_transaction(raw, categories, accounts, merchant_names_by_id_map) for raw in raw_transactions_by_id_map.values())
    snapshot = Snapshot(
        transactions=tuple(sorted(transactions, key=lambda transaction: (transaction.date, transaction.id))),
        categories=categories,
        accounts=accounts,
        balance_adjustment_category_id=None,
    )
    return snapshot.with_balance_adjustment_category(balance_adjustment_category_id)


def _check_pages_complete(pages: list[RawObject]) -> None:
    last_page_count = sum(1 for page in pages if page.get("nextCursor") is None)
    if last_page_count != 1:
        raise IncompletePagesError(
            f"expected exactly 1 page without nextCursor among {len(pages)} pages of 1 query, found {last_page_count}: "
            "a cursor was not followed to the end, or pages of 2 queries share 1 folder"
        )


def read_categories(raw_categories: list[RawObject]) -> tuple[Category, ...]:
    names_by_id_map = {raw_category["id"]: raw_category["name"].strip() for raw_category in raw_categories}
    return tuple(
        Category(
            id=raw_category["id"],
            name=raw_category["name"].strip(),
            parent_id=raw_category.get("parentId"),
            parent_name=names_by_id_map.get(raw_category.get("parentId")),
        )
        for raw_category in raw_categories
    )


def _read_account(raw_account: RawObject) -> Account:
    return Account(id=raw_account["id"], name=raw_account["name"].strip(), instrument=raw_account["instrument"])


def _collect_merchant_names(pages: list[RawObject]) -> dict[str, str]:
    return {
        merchant_id: merchant["name"]
        for page in pages
        for merchant_id, merchant in page.get("references", {}).get("merchants", {}).items()
    }


def _read_transaction(
    raw: RawObject,
    categories: tuple[Category, ...],
    accounts: tuple[Account, ...],
    merchant_names_by_id_map: dict[str, str],
) -> Transaction:
    kind = _read_kind(raw)
    side = raw["expense"] if kind != TransactionKind.INCOME else raw["income"]
    category_id = raw.get("categoryId")
    category_name = next((category.full_name for category in categories if category.id == category_id), None)
    account_name = next((account.name for account in accounts if account.id == side["accountId"]), None)
    if account_name is None:
        raise UnknownAccountError(f"transaction {raw['id']} uses account {side['accountId']}, which the saved accounts do not hold")

    merchant_name = merchant_names_by_id_map.get(raw.get("merchantId") or "", "")

    return Transaction(
        id=raw["id"],
        date=date.fromisoformat(raw["date"]),
        kind=kind,
        account_id=side["accountId"],
        account_name=account_name,
        amount=side["amount"],
        category_id=category_id,
        category_name=category_name,
        payee=raw.get("originalPayee") or merchant_name,
        comment=raw.get("comment") or "",
        is_balance_adjustment=False,
        is_reviewed=raw.get("isReviewed", True) is not False,
        is_synced=bool(raw.get("source")),
    )


def _read_kind(raw: RawObject) -> TransactionKind:
    if raw.get("expense") and raw.get("income"):
        return TransactionKind.TRANSFER
    if raw.get("expense"):
        return TransactionKind.EXPENSE
    return TransactionKind.INCOME
