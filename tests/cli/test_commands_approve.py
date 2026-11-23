import json
from pathlib import Path
from typing import Any

import yaml

from tests.support.zenmoney_responses import CAFE_ID, GROCERIES_ID, read_json
from zenmoney_cleaner.cli.commands import main


def _build_transaction_line(transaction_id: str, current_category: str | None = None, current_category_id: str | None = None) -> dict[str, Any]:
    return {
        "id": transaction_id,
        "date": "2025-11-12",
        "account": "Main Card",
        "amount": -2.9,
        "payee": "SHOP",
        "comment": "",
        "currentCategory": current_category,
        "currentCategoryId": current_category_id,
    }


def _build_change(transaction_id: str, merchant_key: str, confidence: str, current_category_id: str | None = None) -> dict[str, Any]:
    return {
        "merchantKey": merchant_key,
        "transaction": _build_transaction_line(transaction_id, "Groceries" if current_category_id else None, current_category_id),
        "action": "categorize",
        "newCategory": "Cafes & Restaurants",
        "confidence": confidence,
        "source": "rule bakery",
        "upsert": {"id": transaction_id, "categoryId": CAFE_ID},
    }


def _run_approve(tmp_path: Path, raw_proposal: dict[str, Any], *options: str) -> tuple[dict[str, Any], dict[str, Any]]:
    proposal_path = tmp_path / "proposal.json"
    batches_path = tmp_path / "batches.json"
    proposal_path.write_text(json.dumps(raw_proposal), encoding="utf-8")

    main(["approve", "--proposal", str(proposal_path), "--out", str(batches_path), "--home", str(tmp_path), *options])

    verified_path = tmp_path / "verified.yml"
    verified_entries = yaml.safe_load(verified_path.read_text(encoding="utf-8")) if verified_path.exists() else {}
    return read_json(batches_path), verified_entries or {}


def test_should_send_only_changes_of_the_approved_confidence_when_a_minimum_is_given(tmp_path: Path) -> None:
    # given
    changes = [
        _build_change("t-1", "SMOKE CORNER", "high"),
        _build_change("t-2", "CRUMB BAKERY", "medium"),
        _build_change("t-3", None, "low"),
        {"merchantKey": "OVERNIGHT FUND SWEEP", "transaction": _build_transaction_line("t-4"), "action": "delete", "confidence": "high", "deleteId": "t-4"},
    ]

    # when
    batches, _ = _run_approve(tmp_path, {"changes": changes}, "--min-confidence", "medium")

    # then
    assert [upsert["id"] for upsert in batches["upsertBatches"][0]] == ["t-1", "t-2"]
    assert batches["deleteBatches"] == [["t-4"]]


def test_should_leave_out_a_merchant_when_the_user_skips_it(tmp_path: Path) -> None:
    # given
    changes = [_build_change("t-1", "SMOKE CORNER", "high"), _build_change("t-2", "PARCELWORLD", "high")]

    # when
    batches, verified_entries = _run_approve(tmp_path, {"changes": changes}, "--skip", "PARCELWORLD")

    # then
    assert [upsert["id"] for upsert in batches["upsertBatches"][0]] == ["t-1"]
    assert set(verified_entries) == {"t-1"}


def test_should_split_the_updates_into_batches_of_200_when_there_are_more(tmp_path: Path) -> None:
    # given
    change_count = 450
    changes = [_build_change(f"t-{index}", "CAFE PELICAN", "high") for index in range(change_count)]

    # when
    batches, _ = _run_approve(tmp_path, {"changes": changes})

    # then
    assert [len(batch) for batch in batches["upsertBatches"]] == [200, 200, 50]


def test_should_record_the_new_category_as_verified_when_a_change_is_approved(tmp_path: Path) -> None:
    # given
    changes = [_build_change("t-1", "CRUMB BAKERY", "high")]

    # when
    _, verified_entries = _run_approve(tmp_path, {"changes": changes})

    # then
    assert verified_entries["t-1"]["category_id"] == CAFE_ID
    assert verified_entries["t-1"]["by"] == "user approved rule bakery"


def test_should_record_the_current_category_and_send_nothing_when_the_user_keeps_it(tmp_path: Path) -> None:
    # given
    toys_at_supermarket = _build_change("t-1", "HYPERMART", "medium", current_category_id=GROCERIES_ID)

    # when
    batches, verified_entries = _run_approve(tmp_path, {"changes": [toys_at_supermarket]}, "--min-confidence", "low", "--keep", "HYPERMART")

    # then
    assert batches["upsertBatches"] == []
    assert verified_entries["t-1"]["category_id"] == GROCERIES_ID
    assert verified_entries["t-1"]["reason"] == "user kept the current category"


def test_should_record_agreements_as_verified_when_the_proposal_is_approved(tmp_path: Path) -> None:
    # given
    agreement = {"merchantKey": "GREENBASKET", "transaction": _build_transaction_line("t-1", "Groceries", GROCERIES_ID), "source": "rule supermarket"}

    # when
    _, verified_entries = _run_approve(tmp_path, {"changes": [], "agreements": [agreement]})

    # then
    assert verified_entries["t-1"]["by"] == "rule supermarket"


def test_should_mark_confirmed_transactions_reviewed_when_the_mode_is_new(tmp_path: Path) -> None:
    # given
    agreement = {"merchantKey": "GREENBASKET", "transaction": _build_transaction_line("t-1", "Groceries", GROCERIES_ID), "source": "agent"}

    # when
    batches, _ = _run_approve(tmp_path, {"mode": "new-in-zenmoney", "changes": [], "agreements": [agreement]})

    # then
    assert batches["upsertBatches"] == [[{"id": "t-1", "isReviewed": True}]]


def test_should_set_the_category_the_user_chose_when_a_merchant_was_undecided(tmp_path: Path) -> None:
    # given
    undecided = {"merchantKey": "WWW.PARCELWORLD", "transaction": _build_transaction_line("t-1", "Groceries", GROCERIES_ID)}
    raw_proposal = {"changes": [], "undecided": [undecided], "categoriesByKey": {"cafe": {"id": CAFE_ID, "name": "Cafes & Restaurants", "parent_id": None}}}

    # when
    batches, verified_entries = _run_approve(tmp_path, raw_proposal, "--set", "WWW.PARCELWORLD=cafe")

    # then
    assert batches["upsertBatches"] == [[{"id": "t-1", "categoryId": CAFE_ID}]]
    assert verified_entries["t-1"]["category"] == "Cafes & Restaurants"
    assert verified_entries["t-1"]["by"] == "user"


def test_should_mark_an_undecided_merchant_reviewed_when_the_user_keeps_it_in_the_mode_new_in_zenmoney(tmp_path: Path) -> None:
    # given
    undecided = {"merchantKey": "APP STORE", "transaction": _build_transaction_line("t-1", "Groceries", GROCERIES_ID)}

    # when
    batches, verified_entries = _run_approve(
        tmp_path, {"mode": "new-in-zenmoney", "changes": [], "undecided": [undecided]}, "--keep", "APP STORE"
    )

    # then
    assert batches["upsertBatches"] == [[{"id": "t-1", "isReviewed": True}]]
    assert verified_entries["t-1"]["category"] == "Groceries"


def test_should_refuse_the_approval_when_a_chosen_category_key_is_unknown(tmp_path: Path) -> None:
    # given
    undecided = {"merchantKey": "WWW.PARCELWORLD", "transaction": _build_transaction_line("t-1")}
    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_text(json.dumps({"changes": [], "undecided": [undecided], "categoriesByKey": {}}), encoding="utf-8")

    # when
    exit_code = main(["approve", "--proposal", str(proposal_path), "--set", "WWW.PARCELWORLD=hom", "--out", str(tmp_path / "b.json"), "--home", str(tmp_path)])

    # then
    assert exit_code == 1
    assert not (tmp_path / "b.json").exists()


def test_should_keep_every_other_undecided_merchant_when_the_user_keeps_the_rest(tmp_path: Path) -> None:
    # given
    raw_proposal = {
        "changes": [_build_change("t-4", None, "medium", GROCERIES_ID)],
        "undecided": [
            {"merchantKey": None, "transaction": _build_transaction_line("t-1", "Groceries", GROCERIES_ID)},
            {"merchantKey": "WWW.PARCELWORLD", "transaction": _build_transaction_line("t-2", "Groceries", GROCERIES_ID)},
            {"merchantKey": "ECO STORE", "transaction": _build_transaction_line("t-3", "Groceries", GROCERIES_ID)},
        ],
        "categoriesByKey": {"cafe": {"id": CAFE_ID, "name": "Cafes & Restaurants", "parent_id": None}},
    }

    # when
    batches, verified_entries = _run_approve(
        tmp_path, raw_proposal, "--min-confidence", "medium", "--set", "WWW.PARCELWORLD=cafe", "--skip", "ECO STORE", "--keep-other-undecided"
    )

    # then
    assert batches["upsertBatches"] == [[{"id": "t-4", "categoryId": CAFE_ID}, {"id": "t-2", "categoryId": CAFE_ID}]]
    assert sorted(verified_entries) == ["t-1", "t-2", "t-4"]
    assert verified_entries["t-1"]["category"] == "Groceries"


def test_should_add_the_comment_to_the_update_and_the_verified_entry_when_the_user_sets_a_category_with_a_comment(tmp_path: Path) -> None:
    # given
    undecided = {"merchantKey": "OUTLET 6227", "transaction": _build_transaction_line("t-1", "Groceries", GROCERIES_ID)}
    raw_proposal = {"changes": [], "undecided": [undecided], "categoriesByKey": {"cafe": {"id": CAFE_ID, "name": "Cafes & Restaurants", "parent_id": None}}}

    # when
    batches, verified_entries = _run_approve(tmp_path, raw_proposal, "--set", "OUTLET 6227=cafe", "--comment", "OUTLET 6227=Coffee for the team (Outlet)")

    # then
    assert batches["upsertBatches"] == [[{"id": "t-1", "categoryId": CAFE_ID, "comment": "Coffee for the team (Outlet)"}]]
    assert verified_entries["t-1"]["comment"] == "Coffee for the team (Outlet)"


def test_should_append_the_comment_after_the_one_the_transaction_holds_when_the_user_keeps_its_category(tmp_path: Path) -> None:
    # given
    transaction_line = _build_transaction_line("t-1", "Groceries", GROCERIES_ID) | {"comment": "Elm Street 4"}
    undecided = {"merchantKey": "UTILITY CO", "transaction": transaction_line}

    # when
    batches, _ = _run_approve(tmp_path, {"changes": [], "undecided": [undecided]}, "--keep", "UTILITY CO", "--comment", "UTILITY CO=Electricity")

    # then
    assert batches["upsertBatches"] == [[{"id": "t-1", "comment": "Elm Street 4 · Electricity"}]]


def test_should_refuse_the_approval_when_a_comment_names_a_merchant_that_no_decided_row_holds(tmp_path: Path) -> None:
    # given
    undecided = {"merchantKey": "UTILITY CO", "transaction": _build_transaction_line("t-1", "Groceries", GROCERIES_ID)}
    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_text(json.dumps({"changes": [], "undecided": [undecided]}), encoding="utf-8")

    # when
    exit_code = main(["approve", "--proposal", str(proposal_path), "--comment", "UTILITY CO=Electricity", "--out", str(tmp_path / "b.json"), "--home", str(tmp_path)])

    # then
    assert exit_code == 1
    assert not (tmp_path / "b.json").exists()
