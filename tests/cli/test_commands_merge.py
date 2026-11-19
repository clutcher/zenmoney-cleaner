import json
from pathlib import Path

from tests.support.zenmoney_responses import (
    ADJUSTMENT_ID,
    USD_ID,
    build_expense,
    build_income,
    build_page,
    read_json,
    write_fetch,
)
from zenmoney_cleaner.cli.commands import main


def _merge(fetch: Path, snapshot_path: Path) -> int:
    return main([
        "merge",
        "--pages", str(fetch / "pages"),
        "--categories", str(fetch / "categories.json"),
        "--accounts", str(fetch / "accounts.json"),
        "--out", str(snapshot_path),
    ])


def test_should_join_all_pages_into_1_snapshot_when_the_last_page_has_no_cursor(tmp_path: Path) -> None:
    # given
    first_page = build_page([build_expense("t-1", "2025-11-18", 3.12, "GREENBASKET ELM")], next_cursor="c2.next")
    last_page = build_page([
        build_income("t-2", "2025-11-16", 250, "OVERNIGHT FUND SWEEP", USD_ID),
        build_expense("t-3", "2025-11-19", 6.45, category_id=ADJUSTMENT_ID, comment="Account balance auto-adjustment"),
    ])
    fetch = write_fetch(tmp_path, [first_page, last_page])
    snapshot_path = tmp_path / "snapshot.json"

    # when
    exit_code = _merge(fetch, snapshot_path)

    # then
    transactions_by_id_map = {raw["id"]: raw for raw in read_json(snapshot_path)["transactions"]}
    assert exit_code == 0
    assert sorted(transactions_by_id_map) == ["t-1", "t-2", "t-3"]
    assert transactions_by_id_map["t-2"]["account_name"] == "USD"
    assert transactions_by_id_map["t-2"]["kind"] == "income"
    assert transactions_by_id_map["t-3"]["is_balance_adjustment"] is True
    assert transactions_by_id_map["t-1"]["is_balance_adjustment"] is False


def test_should_refuse_the_merge_when_every_page_still_has_a_cursor(tmp_path: Path) -> None:
    # given
    unfinished_page = build_page([build_expense("t-1", "2025-11-18", 3.12, "GREENBASKET ELM")], next_cursor="c2.next")
    fetch = write_fetch(tmp_path, [unfinished_page])
    snapshot_path = tmp_path / "snapshot.json"

    # when
    exit_code = _merge(fetch, snapshot_path)

    # then
    assert exit_code == 1
    assert not snapshot_path.exists()


def test_should_keep_a_transaction_once_when_2_queries_both_return_it(tmp_path: Path) -> None:
    # given
    correction = build_expense("t-2", "2025-11-19", 6.45, category_id=ADJUSTMENT_ID, comment="Account balance auto-adjustment")
    fetch = write_fetch(tmp_path, [build_page([build_expense("t-1", "2025-11-18", 3.12, "GREENBASKET ELM"), correction])])
    history_pages = tmp_path / "history"
    history_pages.mkdir()
    (history_pages / "page-001.json").write_text(json.dumps(build_page([correction])), encoding="utf-8")
    snapshot_path = tmp_path / "snapshot.json"

    # when
    exit_code = main([
        "merge",
        "--pages", str(fetch / "pages"),
        "--pages", str(history_pages),
        "--categories", str(fetch / "categories.json"),
        "--accounts", str(fetch / "accounts.json"),
        "--out", str(snapshot_path),
    ])

    # then
    assert exit_code == 0
    assert sorted(raw["id"] for raw in read_json(snapshot_path)["transactions"]) == ["t-1", "t-2"]


def test_should_refuse_the_merge_when_a_transaction_uses_an_unsaved_account(tmp_path: Path) -> None:
    # given
    unsaved_account_id = "11111111-2222-4333-8444-555555555555"
    page = build_page([build_expense("t-1", "2025-11-18", 3.12, "GREENBASKET ELM", account_id=unsaved_account_id)])
    fetch = write_fetch(tmp_path, [page])
    snapshot_path = tmp_path / "snapshot.json"

    # when
    exit_code = _merge(fetch, snapshot_path)

    # then
    assert exit_code == 1
    assert not snapshot_path.exists()
