from pathlib import Path
from typing import Any

import pytest

from tests.support.zenmoney_responses import (
    CATEGORIES_RESPONSE,
    CONFIG_TEXT,
    GROCERIES_ID,
    YEN_ID,
    build_correction,
    build_expense,
    build_page,
    read_json,
    write_fetch,
    write_home,
)
from zenmoney_cleaner.cli.commands import main

_RESPONSE_WITHOUT_ADJUSTMENT_ID = CATEGORIES_RESPONSE | {"balanceAdjustmentCategoryId": None}


def _run_corrections(
    tmp_path: Path, transactions: list[dict[str, Any]], categories_response: dict[str, Any] = CATEGORIES_RESPONSE, config_text: str = CONFIG_TEXT
) -> int:
    fetch = write_fetch(tmp_path, [build_page(transactions)], categories_response)
    snapshot_path = tmp_path / "snapshot.json"
    main(["merge", "--pages", str(fetch / "pages"), "--categories", str(fetch / "categories.json"), "--accounts", str(fetch / "accounts.json"), "--out", str(snapshot_path)])
    return main(["corrections", "--snapshot", str(snapshot_path), "--out", str(tmp_path / "corrections"), "--home", str(write_home(tmp_path, config_text))])


def _find_corrections(tmp_path: Path, transactions: list[dict[str, Any]]) -> dict[str, Any]:
    _run_corrections(tmp_path, transactions)
    return read_json(tmp_path / "corrections" / "proposal.json")


def test_should_propose_deleting_a_run_that_adds_up_to_0_when_an_older_correction_stays_open(tmp_path: Path) -> None:
    # given
    old_open_correction = build_correction("c-old", "2025-02-28", -187.40)
    later_pair = [build_correction("c-1", "2025-08-31", -46.20), build_correction("c-2", "2025-09-03", 46.21)]

    # when
    proposal = _find_corrections(tmp_path, [old_open_correction, *later_pair])

    # then
    assert sorted(change["deleteId"] for change in proposal["changes"]) == ["c-1", "c-2"]
    assert [correction["id"] for correction in proposal["openChains"][0]["corrections"]] == ["c-old"]


def test_should_leave_an_entry_alone_when_the_user_typed_it_into_the_adjustment_category(tmp_path: Path) -> None:
    # given
    typed_entry = build_correction("c-typed", "2025-08-01", -100, source=None)
    synced_pair = [build_correction("c-1", "2025-08-02", -100), build_correction("c-2", "2025-08-03", 100)]

    # when
    proposal = _find_corrections(tmp_path, [typed_entry, *synced_pair])

    # then
    assert sorted(change["deleteId"] for change in proposal["changes"]) == ["c-1", "c-2"]
    assert proposal["openChains"] == []


def test_should_list_the_purchases_that_add_up_to_an_open_correction_when_they_fall_in_the_window(tmp_path: Path) -> None:
    # given
    purchases = [build_expense("p-1", "2025-11-16", 3.15, "GREENBASKET"), build_expense("p-2", "2025-11-17", 4.60, "QMEXPELM33")]
    open_correction = build_correction("c-1", "2025-11-19", -7.75)

    # when
    proposal = _find_corrections(tmp_path, [*purchases, open_correction])

    # then
    open_chain = proposal["openChains"][0]
    matched_ids = [[transaction["id"] for transaction in transaction_set] for transaction_set in open_chain["matches"][0]["transactionSets"]]
    assert matched_ids == [["p-1", "p-2"]]
    assert open_chain["pending"] is True


def test_should_report_a_real_difference_when_the_open_correction_is_old(tmp_path: Path) -> None:
    # given
    old_open_correction = build_correction("c-1", "2025-03-15", -31.80)
    newest_purchase = build_expense("p-1", "2025-11-19", 2.5, "CAFE ORBIT")

    # when
    proposal = _find_corrections(tmp_path, [old_open_correction, newest_purchase])

    # then
    assert proposal["changes"] == []
    assert proposal["openChains"][0]["pending"] is False
    assert proposal["openChains"][0]["residual"] == -31.8


def test_should_take_the_category_named_in_the_config_when_zenmoney_reports_no_adjustment_category(tmp_path: Path) -> None:
    # given
    config_text = CONFIG_TEXT + "corrections: {adjustment_category: Balance adjustment}\n"
    synced_pair = [build_correction("c-1", "2025-08-02", -100), build_correction("c-2", "2025-08-03", 100)]

    # when
    exit_code = _run_corrections(tmp_path, synced_pair, _RESPONSE_WITHOUT_ADJUSTMENT_ID, config_text)

    # then
    proposal = read_json(tmp_path / "corrections" / "proposal.json")
    assert exit_code == 0
    assert sorted(change["deleteId"] for change in proposal["changes"]) == ["c-1", "c-2"]


def test_should_stop_and_name_the_likely_category_when_neither_zenmoney_nor_the_config_names_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given
    synced_pair = [build_correction("c-1", "2025-08-02", -100), build_correction("c-2", "2025-08-03", 100)]
    purchase = build_expense("p-1", "2025-08-02", 3.15, "GREENBASKET", category_id=GROCERIES_ID)

    # when
    exit_code = _run_corrections(tmp_path, [*synced_pair, purchase], _RESPONSE_WITHOUT_ADJUSTMENT_ID)

    # then
    error_text = capsys.readouterr().err
    assert exit_code == 1
    assert "Balance adjustment (2 of 2)" in error_text
    assert "Groceries" not in error_text


def test_should_close_a_chain_within_1_yen_when_the_account_holds_a_currency_without_decimals(tmp_path: Path) -> None:
    # given
    yen_pair = [build_correction("c-1", "2025-08-02", -1500, account_id=YEN_ID), build_correction("c-2", "2025-08-03", 1501, account_id=YEN_ID)]

    # when
    proposal = _find_corrections(tmp_path, yen_pair)

    # then
    assert sorted(change["deleteId"] for change in proposal["changes"]) == ["c-1", "c-2"]
