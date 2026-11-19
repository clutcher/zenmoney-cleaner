from pathlib import Path
from typing import Any

from tests.support.zenmoney_responses import CAFE_ID, build_expense, build_page, read_json, write_fetch, write_home
from zenmoney_cleaner.cli.commands import main


def _merge_with_history(directory: Path, history_path: Path, transactions: list[dict[str, Any]], fetched_from: str, fetched_to: str) -> Path:
    directory.mkdir()
    fetch = write_fetch(directory, [build_page(transactions)])
    snapshot_path = directory / "snapshot.json"
    main([
        "merge",
        "--pages", str(fetch / "pages"),
        "--categories", str(fetch / "categories.json"),
        "--accounts", str(fetch / "accounts.json"),
        "--out", str(snapshot_path),
        "--history", str(history_path),
        "--fetched-from", fetched_from,
        "--fetched-to", fetched_to,
    ])
    return snapshot_path


def test_should_show_the_categories_of_earlier_months_when_only_the_history_holds_them(tmp_path: Path) -> None:
    # given
    home = write_home(tmp_path)
    history_path = home / "history.json"
    _merge_with_history(tmp_path / "first", history_path, [build_expense("t-1", "2025-09-01", 2.8, "CAFETERIA LUMEN", CAFE_ID)], "2025-08-19", "2025-11-10")
    weekly_snapshot_path = _merge_with_history(
        tmp_path / "weekly", history_path, [build_expense("t-2", "2025-11-18", 2.8, "CAFETERIA LUMEN")], "2025-11-03", "2025-11-19"
    )
    out = tmp_path / "run"

    # when
    main(["prepare", "--snapshot", str(weekly_snapshot_path), "--out", str(out), "--home", str(home), "--mode", "without-category"])

    # then
    merchant = read_json(out / "categorize" / "tasks" / "task-001.json")["merchants"][0]
    assert [transaction["id"] for transaction in merchant["transactions"]] == ["t-2"]
    assert merchant["otherCategories"] == {"Cafes & Restaurants": 1}


def test_should_drop_a_transaction_from_the_history_when_a_fetch_of_its_range_no_longer_returns_it(tmp_path: Path) -> None:
    # given
    history_path = tmp_path / "history.json"
    first_transactions = [build_expense("t-old", "2025-09-01", 2.8, "CAFETERIA LUMEN", CAFE_ID), build_expense("t-gone", "2025-11-10", 4, "CAFE ORBIT")]
    _merge_with_history(tmp_path / "first", history_path, first_transactions, "2025-08-19", "2025-11-10")

    # when
    _merge_with_history(tmp_path / "weekly", history_path, [build_expense("t-new", "2025-11-18", 2.8, "CAFETERIA LUMEN")], "2025-11-03", "2025-11-19")

    # then
    assert [entry["id"] for entry in read_json(history_path)["transactions"]] == ["t-old", "t-new"]


def test_should_refuse_the_merge_when_the_history_is_given_without_the_fetched_range(tmp_path: Path) -> None:
    # given
    fetch = write_fetch(tmp_path, [build_page([build_expense("t-1", "2025-11-18", 2.8, "CAFETERIA LUMEN")])])

    # when
    exit_code = main([
        "merge",
        "--pages", str(fetch / "pages"),
        "--categories", str(fetch / "categories.json"),
        "--accounts", str(fetch / "accounts.json"),
        "--out", str(tmp_path / "snapshot.json"),
        "--history", str(tmp_path / "history.json"),
    ])

    # then
    assert exit_code == 1
    assert not (tmp_path / "history.json").exists()
