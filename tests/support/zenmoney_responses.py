import json
from pathlib import Path
from typing import Any

CAFE_ID = "1168942e-c881-4146-829c-c6015ea70bc1"
GROCERIES_ID = "5a6aa2ca-3ea7-4648-af6f-19b794245bc0"
CLOTHING_ID = "f2a435b6-1b90-4d05-a5fb-5e97242170cc"
PERSONAL_ID = "edc6136a-2717-4fbc-8439-dab04f83fd09"
COSMETICS_ID = "a38a0d75-2e32-4119-af13-ed6d3458dd12"
ADJUSTMENT_ID = "3841d2f2-5cc9-48db-bd92-34f02a54a36f"
CARD_ID = "d35f63ad-bc45-42df-9712-3672fb40b683"
USD_ID = "95b317b4-a286-4c8b-bd9a-93e326c279f7"
SAVINGS_ID = "da79d28b-37e3-4427-be25-544c8e5280bf"
YEN_ID = "29a7a447-edb7-48b0-9197-cced6e78ab91"

CATEGORIES_RESPONSE = {
    "balanceAdjustmentCategoryId": ADJUSTMENT_ID,
    "data": [
        {"id": CAFE_ID, "name": "Cafes & Restaurants", "parentId": None},
        {"id": GROCERIES_ID, "name": "Groceries", "parentId": None},
        {"id": CLOTHING_ID, "name": "Clothing", "parentId": None},
        {"id": PERSONAL_ID, "name": "Personal", "parentId": None},
        {"id": COSMETICS_ID, "name": "Cosmetics", "parentId": PERSONAL_ID},
        {"id": ADJUSTMENT_ID, "name": "Balance adjustment", "parentId": None},
    ],
}

ACCOUNTS_RESPONSE = {
    "data": [
        {"id": CARD_ID, "name": "Main Card", "instrument": "EUR"},
        {"id": USD_ID, "name": "USD ", "instrument": "USD"},
        {"id": SAVINGS_ID, "name": "Rainy Day Fund", "instrument": "EUR"},
        {"id": YEN_ID, "name": "Travel Yen", "instrument": "JPY"},
    ]
}

CONFIG_TEXT = """
location: {city: Lindenport, country: Examplia, country_code: XA}
categories:
  cafe: Cafes & Restaurants
  groceries: Groceries
  clothing: Clothing
  personal: Personal
  personal_cosmetics: Cosmetics
payee:
  strip: ['\\s+XA$', '\\s{2,}[A-Z .]+$', '^(MP\\*\\*|SQ \\*)', '\\s+\\d{2,}$']
rules:
  - name: fund-sweep
    when: {payee: OVERNIGHT FUND SWEEP, account: USD}
    action: delete
    reason: the fund moves are removed
  - name: rainy-day-fund
    when: {comment: rainy day fund}
    action: transfer
    to_account: Rainy Day Fund
    reason: weekly saving
  - name: tobacco
    when: {payee: [SMOKE CORNER NO.4, smoke shop old market]}
    category: personal
    reason: cigarettes
"""

POLICY_TEXT = "# How I categorize\n\n- A cafeteria is Cafes & Restaurants.\n"


def build_expense(
    transaction_id: str,
    day: str,
    amount: float,
    payee: str = "",
    category_id: str | None = None,
    account_id: str = CARD_ID,
    comment: str | None = None,
) -> dict[str, Any]:
    return {
        "id": transaction_id,
        "date": day,
        "expense": {"accountId": account_id, "amount": amount},
        "categoryId": category_id,
        "originalPayee": payee or None,
        "comment": comment,
    }


def build_income(transaction_id: str, day: str, amount: float, payee: str, account_id: str) -> dict[str, Any]:
    return {"id": transaction_id, "date": day, "income": {"accountId": account_id, "amount": amount}, "originalPayee": payee}


def build_correction(
    transaction_id: str, day: str, signed_amount: float, source: str | None = "plugin", account_id: str = CARD_ID
) -> dict[str, Any]:
    side = "expense" if signed_amount < 0 else "income"
    return {
        "id": transaction_id,
        "date": day,
        side: {"accountId": account_id, "amount": abs(signed_amount)},
        "categoryId": ADJUSTMENT_ID,
        "comment": "Account balance auto-adjustment",
        "source": source,
    }


def build_page(transactions: list[dict[str, Any]], next_cursor: str | None = None) -> dict[str, Any]:
    return {"data": transactions, "references": {}, "nextCursor": next_cursor}


def write_home(directory: Path, config_text: str = CONFIG_TEXT) -> Path:
    home = directory / "home"
    home.mkdir()
    (home / "config.yml").write_text(config_text, encoding="utf-8")
    (home / "policy.md").write_text(POLICY_TEXT, encoding="utf-8")
    return home


def write_fetch(directory: Path, pages: list[dict[str, Any]], categories_response: dict[str, Any] = CATEGORIES_RESPONSE) -> Path:
    fetch = directory / "fetch"
    (fetch / "pages").mkdir(parents=True)
    for index, page in enumerate(pages, start=1):
        _write_json(page, fetch / "pages" / f"page-{index:03}.json")
    _write_json(categories_response, fetch / "categories.json")
    _write_json(ACCOUNTS_RESPONSE, fetch / "accounts.json")
    return fetch


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(raw: Any, path: Path) -> None:
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
