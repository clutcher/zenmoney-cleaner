from pathlib import Path

from tests.support.categorizing_run import start_run
from tests.support.zenmoney_responses import CAFE_ID, CARD_ID, USD_ID, build_expense, build_income


def _list_task_transaction_ids(run_tasks: list[dict]) -> list[str]:
    return sorted(transaction["id"] for task in run_tasks for merchant in task["merchants"] for transaction in merchant["transactions"])


def test_should_take_whole_months_when_the_period_is_given_as_months(tmp_path: Path) -> None:
    # given
    coffees = [
        build_expense("t-jul", "2025-07-31", 2.8, "CAFETERIA LUMEN", CAFE_ID),
        build_expense("t-aug", "2025-08-01", 2.8, "CAFETERIA LUMEN", CAFE_ID),
        build_expense("t-oct", "2025-10-31", 2.8, "CAFETERIA LUMEN", CAFE_ID),
        build_expense("t-nov", "2025-11-01", 2.8, "CAFETERIA LUMEN", CAFE_ID),
    ]
    run = start_run(tmp_path, coffees, "recheck-all")

    # when
    run.run("prepare", "--from", "2025-08", "--to", "2025-10")

    # then
    assert _list_task_transaction_ids(run.read_tasks("categorize")) == ["t-aug", "t-oct"]


def test_should_take_only_the_named_account_and_type_when_they_are_given(tmp_path: Path) -> None:
    # given
    card_coffee = build_expense("t-card", "2025-09-01", 2.8, "CAFETERIA LUMEN", CAFE_ID)
    other_coffee = build_expense("t-other", "2025-09-01", 2.8, "CAFETERIA LUMEN", CAFE_ID, account_id=USD_ID)
    card_refund = build_income("t-refund", "2025-09-02", 2.8, "CAFETERIA LUMEN", CARD_ID)
    run = start_run(tmp_path, [card_coffee, other_coffee, card_refund], "recheck-all")

    # when
    run.run("prepare", "--account", "Main Card", "--type", "expense")

    # then
    assert _list_task_transaction_ids(run.read_tasks("categorize")) == ["t-card"]


def test_should_take_only_transactions_shown_as_new_when_the_mode_is_new_in_zenmoney(tmp_path: Path) -> None:
    # given
    reviewed_coffee = build_expense("t-old", "2025-11-01", 2.8, "CAFETERIA LUMEN", CAFE_ID) | {"isReviewed": True}
    new_coffee = build_expense("t-new", "2025-11-18", 2.8, "CAFETERIA LUMEN", CAFE_ID) | {"isReviewed": False}
    run = start_run(tmp_path, [reviewed_coffee, new_coffee], "new-in-zenmoney")

    # when
    run.run("prepare")

    # then
    assert _list_task_transaction_ids(run.read_tasks("categorize")) == ["t-new"]
