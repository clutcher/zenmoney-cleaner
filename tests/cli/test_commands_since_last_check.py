import json
from pathlib import Path

from tests.support.categorizing_run import start_run
from tests.support.zenmoney_responses import CAFE_ID, build_expense, read_json
from zenmoney_cleaner.cli.commands import main

_SURE_CAFE = {"category": "cafe", "confidence": "high", "reason": "the name says cafeteria"}


def _list_task_transaction_ids(tasks: list[dict]) -> list[str]:
    return sorted(transaction["id"] for task in tasks for merchant in task["merchants"] for transaction in merchant["transactions"])


def test_should_record_the_newest_checked_day_when_the_user_approves_a_run(tmp_path: Path) -> None:
    # given
    coffees = [build_expense("t-1", "2025-11-01", 2.8, "CAFETERIA LUMEN", CAFE_ID), build_expense("t-2", "2025-11-10", 2.8, "CAFETERIA LUMEN")]
    run = start_run(tmp_path, coffees, "recheck-all")
    run.run("prepare")
    run.answer_every_task("categorize", {"t-1": _SURE_CAFE, "t-2": _SURE_CAFE})
    run.run("route")
    run.run("verify")
    run.run("propose")

    # when
    main(["approve", "--proposal", str(run.out / "proposal.json"), "--out", str(tmp_path / "batches.json"), "--home", str(run.home)])

    # then
    assert read_json(run.home / "history.json")["lastCheck"] == "2025-11-10"


def test_should_take_the_transactions_from_the_day_of_the_last_check_when_the_mode_is_since_last_check(tmp_path: Path) -> None:
    # given
    coffees = [build_expense(f"t-{day}", f"2025-11-{day:02}", 2.8, "CAFETERIA LUMEN", CAFE_ID) for day in (9, 10, 12)]
    run = start_run(tmp_path, coffees, "since-last-check")
    (run.home / "history.json").write_text(json.dumps({"lastCheck": "2025-11-10", "transactions": []}), encoding="utf-8")

    # when
    run.run("prepare")

    # then
    assert _list_task_transaction_ids(run.read_tasks("categorize")) == ["t-10", "t-12"]


def test_should_stop_with_an_error_when_no_check_is_recorded_and_the_mode_is_since_last_check(tmp_path: Path) -> None:
    # given
    run = start_run(tmp_path, [build_expense("t-1", "2025-11-12", 2.8, "CAFETERIA LUMEN")], "since-last-check")

    # when
    exit_code = run.run("prepare")

    # then
    assert exit_code == 1
    assert not (run.out / "categorize").exists()


def test_should_record_the_day_of_the_oldest_row_left_open_when_the_user_skips_a_merchant(tmp_path: Path) -> None:
    # given
    transactions = [build_expense("t-1", "2025-11-03", 61.2, "MAPLE THREAD BOUTIQUE"), build_expense("t-2", "2025-11-10", 2.8, "CAFETERIA LUMEN")]
    run = start_run(tmp_path, transactions, "since-last-check")
    (run.home / "history.json").write_text(json.dumps({"lastCheck": "2025-11-01", "transactions": []}), encoding="utf-8")
    run.run("prepare")
    unknown_answer = {"category": None, "confidence": "low", "reason": "an unknown shop", "searchable": False}
    run.answer_every_task("categorize", {"t-1": unknown_answer, "t-2": _SURE_CAFE})
    run.run("route")
    run.run("verify")
    run.run("propose")

    # when
    main(["approve", "--proposal", str(run.out / "proposal.json"), "--out", str(tmp_path / "batches.json"), "--home", str(run.home)])

    # then
    assert read_json(run.home / "history.json")["lastCheck"] == "2025-11-03"
