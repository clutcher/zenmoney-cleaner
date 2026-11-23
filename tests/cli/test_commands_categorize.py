from pathlib import Path

import yaml

from tests.support.categorizing_run import start_run
from tests.support.zenmoney_responses import (
    CAFE_ID,
    CLOTHING_ID,
    COSMETICS_ID,
    GROCERIES_ID,
    SAVINGS_ID,
    USD_ID,
    PERSONAL_ID,
    build_expense,
    build_income,
    read_json,
)

_SURE_CAFE = {"category": "cafe", "confidence": "high", "reason": "the name says cafeteria"}


def test_should_decide_by_rule_without_the_agent_when_a_strict_rule_matches(tmp_path: Path) -> None:
    # given
    tobacco_purchase = build_expense("t-1", "2025-11-10", 12, "SMOKE CORNER NO.4           LINDENPORT     XA")
    run = start_run(tmp_path, [tobacco_purchase], "without-category")

    # when
    run.run("prepare")
    run.run("route")
    exit_code = run.run("propose")

    # then
    change = run.read_changes_by_id_map()["t-1"]
    assert exit_code == 0
    assert run.read_tasks("categorize") == []
    assert change["upsert"] == {"id": "t-1", "categoryId": PERSONAL_ID}
    assert change["source"] == "rule tobacco"


def test_should_propose_deletion_and_a_transfer_when_rules_ask_for_them(tmp_path: Path) -> None:
    # given
    fund_withdrawal = build_income("t-1", "2025-11-16", 250, "OVERNIGHT FUND SWEEP", USD_ID)
    weekly_saving = build_expense("t-2", "2025-10-12", 15, comment="To Rainy Day Fund")
    run = start_run(tmp_path, [fund_withdrawal, weekly_saving], "without-category")

    # when
    run.run("prepare")
    run.run("route")
    run.run("propose")

    # then
    changes_by_id_map = run.read_changes_by_id_map()
    assert changes_by_id_map["t-1"]["deleteId"] == "t-1"
    assert changes_by_id_map["t-2"]["upsert"]["income"] == {"accountId": SAVINGS_ID, "amount": 15}


def test_should_hand_only_empty_transactions_to_the_agent_when_the_mode_is_without_category(tmp_path: Path) -> None:
    # given
    filed_coffee = build_expense("t-1", "2025-11-01", 2.8, "CAFETERIA LUMEN", CAFE_ID)
    new_coffee = build_expense("t-2", "2025-11-02", 2.8, "CAFETERIA LUMEN")
    run = start_run(tmp_path, [filed_coffee, new_coffee], "without-category")

    # when
    run.run("prepare")

    # then
    merchant = run.read_tasks("categorize")[0]["merchants"][0]
    assert [transaction["id"] for transaction in merchant["transactions"]] == ["t-2"]
    assert merchant["otherCategories"] == {"Cafes & Restaurants": 1}


def test_should_tell_the_agent_of_a_monthly_payment_when_the_amount_repeats_each_month(tmp_path: Path) -> None:
    # given
    gym_fees = [build_expense(f"t-{month}", f"2025-{month:02}-05", 34.5, "IRONLEAF GYM", GROCERIES_ID) for month in (8, 9, 10, 11)]
    run = start_run(tmp_path, gym_fees, "recheck-all")

    # when
    run.run("prepare")

    # then
    habit = run.read_tasks("categorize")[0]["merchants"][0]["habit"]
    assert habit == {"paymentsInSnapshot": 4, "months": 4, "usualAmount": 34.5, "monthlySameAmount": True}


def test_should_confirm_the_category_without_research_when_the_agent_agrees_with_high_confidence(tmp_path: Path) -> None:
    # given
    filed_coffee = build_expense("t-1", "2025-11-01", 2.8, "CAFETERIA LUMEN", CAFE_ID)
    run = start_run(tmp_path, [filed_coffee], "recheck-all")
    run.run("prepare")
    run.answer_every_task("categorize", {"t-1": _SURE_CAFE})

    # when
    run.run("route")
    run.run("verify")
    run.run("propose")

    # then
    assert run.read_tasks("research") == []
    assert [agreement["transaction"]["id"] for agreement in run.read_proposal()["agreements"]] == ["t-1"]


def test_should_research_the_merchant_and_judge_again_when_the_agent_is_unsure(tmp_path: Path) -> None:
    # given
    unknown_shop = build_expense("t-1", "2025-11-18", 61.2, "MAPLE THREAD BOUTIQUE")
    run = start_run(tmp_path, [unknown_shop], "without-category")
    run.run("prepare")
    run.answer_every_task("categorize", {"t-1": {"category": None, "confidence": "low", "reason": "an unknown shop"}})

    # when
    run.run("route")
    research_task = run.read_tasks("research")[0]
    research_answer = {"merchant": research_task["merchant"], "place": "clothing shop", "source": "https://maps", "trust": "medium"}
    run.write_answer("research", "merchant-001.json", research_answer)
    run.answer_every_task("rejudge", {"t-1": {"category": "clothing", "confidence": "high", "reason": "a clothing shop by the map listing"}})
    run.run("verify")
    run.run("propose")

    # then
    assert research_task["merchant"] == "MAPLE THREAD BOUTIQUE"
    assert run.read_tasks("rejudge")[0]["research"].endswith("research/answers/merchant-001.json")
    assert run.read_changes_by_id_map()["t-1"]["upsert"]["categoryId"] == CLOTHING_ID


def test_should_judge_again_with_the_known_place_without_the_researcher_when_the_merchant_was_researched_before(tmp_path: Path) -> None:
    # given
    unknown_shop = build_expense("t-1", "2025-11-18", 61.2, "MAPLE THREAD BOUTIQUE")
    run = start_run(tmp_path, [unknown_shop], "without-category")
    (run.home / "places.yml").write_text(
        "MAPLE THREAD BOUTIQUE: {place: clothing shop, source: 'https://maps', trust: medium, researched: '2025-10-01'}\n",
        encoding="utf-8",
    )
    run.run("prepare")
    run.answer_every_task("categorize", {"t-1": {"category": None, "confidence": "low", "reason": "an unknown shop"}})

    # when
    run.run("route")

    # then
    jobs_text = (run.out / "research" / "jobs.workflow.js").read_text(encoding="utf-8")
    known_place = read_json(run.out / "research" / "answers" / "merchant-001.json")
    assert '"agent": "researcher"' not in jobs_text
    assert '"agent": "categorizer"' in jobs_text
    assert known_place["place"] == "clothing shop"
    assert known_place["researchedOn"] == "2025-10-01"


def test_should_remember_the_researched_place_when_the_research_is_done(tmp_path: Path) -> None:
    # given
    unknown_shop = build_expense("t-1", "2025-11-18", 61.2, "MAPLE THREAD BOUTIQUE")
    run = start_run(tmp_path, [unknown_shop], "without-category")
    run.run("prepare")
    run.answer_every_task("categorize", {"t-1": {"category": None, "confidence": "low", "reason": "an unknown shop"}})
    run.run("route")
    research_answer = {"merchant": "MAPLE THREAD BOUTIQUE", "place": "clothing shop", "source": None, "trust": "low"}
    run.write_answer("research", "merchant-001.json", research_answer)
    run.answer_every_task("rejudge", {"t-1": {"category": "clothing", "confidence": "high", "reason": "a clothing shop"}})

    # when
    run.run("verify")

    # then
    known_places = yaml.safe_load((run.home / "places.yml").read_text(encoding="utf-8"))
    assert known_places["MAPLE THREAD BOUTIQUE"]["place"] == "clothing shop"
    assert known_places["MAPLE THREAD BOUTIQUE"]["trust"] == "low"


def test_should_hand_a_change_of_the_user_category_to_the_verifier_when_the_agent_disagrees(tmp_path: Path) -> None:
    # given
    tobacco_filed_as_groceries = build_expense("t-1", "2025-11-10", 12, "SMOKE STOP RIVER LANE", GROCERIES_ID)
    run = start_run(tmp_path, [tobacco_filed_as_groceries], "recheck-all")
    run.run("prepare")
    run.answer_every_task("categorize", {"t-1": {"category": "personal", "confidence": "high", "reason": "a tobacco shop"}})
    run.run("route")

    # when
    run.run("verify")

    # then
    proposed_change = run.read_tasks("verify")[0]["proposedChanges"][0]
    assert proposed_change == {
        "id": "t-1",
        "currentCategory": "Groceries",
        "proposedCategory": "Personal",
        "confidence": "high",
        "reason": "a tobacco shop",
    }


def test_should_keep_the_user_category_when_the_verifier_rejects_the_change(tmp_path: Path) -> None:
    # given
    clothes_at_hypermarket = build_expense("t-1", "2025-11-10", 42, "HYPERMART EAST", CLOTHING_ID)
    run = start_run(tmp_path, [clothes_at_hypermarket], "recheck-all")
    run.run("prepare")
    run.answer_every_task("categorize", {"t-1": {"category": "groceries", "confidence": "high", "reason": "a supermarket"}})
    run.run("route")
    run.run("verify")
    run.write_answer("verify", "merchant-001.json", [{"id": "t-1", "decision": "reject", "reason": "a hypermarket also sells clothes"}])

    # when
    run.run("propose")

    # then
    assert run.read_proposal()["changes"] == []
    assert "a hypermarket also sells clothes" in (run.out / "proposal.md").read_text(encoding="utf-8")


def test_should_leave_a_user_category_undecided_when_the_agent_only_guesses(tmp_path: Path) -> None:
    # given
    taxi_filed_by_user = build_expense("t-1", "2025-08-29", 18, category_id=CAFE_ID, comment="Taxi")
    run = start_run(tmp_path, [taxi_filed_by_user], "recheck-all")
    run.run("prepare")
    run.answer_every_task("categorize", {"t-1": {"category": "personal", "confidence": "low", "reason": "a round amount"}})
    run.run("route")
    run.write_answer("research", "merchant-001.json", {"merchant": None, "place": None, "source": None, "trust": "none"})
    run.answer_every_task("rejudge", {"t-1": {"category": "personal", "confidence": "low", "reason": "a round amount"}})

    # when
    run.run("verify")
    run.run("propose")

    # then
    assert run.read_proposal()["changes"] == []
    assert run.read_tasks("verify") == []


def test_should_skip_a_transaction_when_its_category_is_verified(tmp_path: Path) -> None:
    # given
    coffee_filed_as_groceries = build_expense("t-1", "2025-11-10", 2.8, "CAFETERIA LUMEN", GROCERIES_ID)
    verified_text = f"t-1: {{category: Groceries, category_id: {GROCERIES_ID}, by: user, payee: CAFETERIA LUMEN, reason: user kept it}}\n"
    run = start_run(tmp_path, [coffee_filed_as_groceries], "recheck-all", verified_text=verified_text)

    # when
    run.run("prepare")

    # then
    assert run.read_tasks("categorize") == []


def test_should_show_confirmed_examples_to_the_agent_when_the_user_verified_similar_transactions(tmp_path: Path) -> None:
    # given
    new_branch = build_expense("t-2", "2025-11-12", 3.9, "QMEXPELM33")
    verified_text = (
        f"t-1: {{category: Groceries, category_id: {GROCERIES_ID}, by: user, payee: QMEXPOAK26, "
        "reason: Quickmart Express, confirmed: '2025-11-19'}\n"
    )
    run = start_run(tmp_path, [new_branch], "without-category", verified_text=verified_text)

    # when
    run.run("prepare")

    # then
    assert run.read_tasks("categorize")[0]["confirmedExamples"] == ["QMEXPOAK26 → Groceries: Quickmart Express"]


def test_should_write_a_rerun_job_with_the_problem_when_the_agent_leaves_a_transaction_unanswered(tmp_path: Path) -> None:
    # given
    coffees = [build_expense("t-1", "2025-11-01", 2.8, "CAFETERIA LUMEN"), build_expense("t-2", "2025-11-02", 2.8, "CAFETERIA LUMEN")]
    run = start_run(tmp_path, coffees, "without-category")
    run.run("prepare")
    run.write_answer("categorize", "task-001.json", [{"id": "t-1"} | _SURE_CAFE])

    # when
    exit_code = run.run("route")

    # then
    rerun_jobs_text = (run.out / "categorize" / "jobs-again.workflow.js").read_text(encoding="utf-8")
    task = run.read_tasks("categorize")[0]
    assert exit_code == 2
    assert "task-001.json" in rerun_jobs_text
    assert task["problemsOfTheLastAnswer"] == ["no answer for the transactions ['t-2']"]
    assert not (run.out / "categorize" / "answers" / "task-001.json").exists()


def test_should_route_on_when_the_rerun_job_answers_well(tmp_path: Path) -> None:
    # given
    coffee = build_expense("t-1", "2025-11-01", 2.8, "CAFETERIA LUMEN")
    run = start_run(tmp_path, [coffee], "without-category")
    run.run("prepare")
    run.answer_every_task("categorize", {"t-1": {"category": "coffee", "confidence": "high", "reason": "a cafe"}})
    run.run("route")
    run.answer_every_task("categorize", {"t-1": _SURE_CAFE})

    # when
    exit_code = run.run("route")

    # then
    assert exit_code == 0
    assert run.read_tasks("research") == []
    assert not (run.out / "categorize" / "jobs-again.workflow.js").exists()


def test_should_stop_with_an_error_when_the_agent_fails_the_same_job_after_2_reruns(tmp_path: Path) -> None:
    # given
    coffee = build_expense("t-1", "2025-11-01", 2.8, "CAFETERIA LUMEN")
    run = start_run(tmp_path, [coffee], "without-category")
    run.run("prepare")
    unknown_key_answer = {"t-1": {"category": "coffee", "confidence": "high", "reason": "a cafe"}}
    for _ in range(2):
        run.answer_every_task("categorize", unknown_key_answer)
        run.run("route")
    run.answer_every_task("categorize", unknown_key_answer)

    # when
    exit_code = run.run("route")

    # then
    assert exit_code == 1


def test_should_leave_a_merchant_unresearched_when_the_agent_finds_nothing_to_search(tmp_path: Path) -> None:
    # given
    payment_to_a_person = build_expense("t-1", "2025-11-04", 8.4, "MARTA LOVELL QUINN", GROCERIES_ID)
    run = start_run(tmp_path, [payment_to_a_person], "recheck-all")
    run.run("prepare")
    unsearchable_answer = {"category": None, "confidence": "low", "reason": "a private person", "searchable": False}
    run.answer_every_task("categorize", {"t-1": unsearchable_answer})

    # when
    run.run("route")
    run.run("verify")
    run.run("propose")

    # then
    assert run.read_tasks("research") == []
    assert run.read_proposal()["undecided"][0]["merchantKey"] == "MARTA LOVELL QUINN"


def test_should_hand_the_agent_only_the_country_when_the_location_names_no_city(tmp_path: Path) -> None:
    # given
    config_without_city = "location: {country: Examplia, country_code: XA}\ncategories: {cafe: Cafes & Restaurants}\n"
    run = start_run(tmp_path, [build_expense("t-1", "2025-11-12", 2.9, "CRUMB BAKERY")], "without-category", config_text=config_without_city)

    # when
    exit_code = run.run("prepare")

    # then
    assert exit_code == 0
    assert run.read_tasks("categorize")[0]["location"] == {"country": "Examplia", "country_code": "XA", "city": None}


def test_should_stop_with_an_error_when_a_rule_names_an_unknown_category(tmp_path: Path) -> None:
    # given
    config_with_typo = """
location: {city: Lindenport, country: Examplia, country_code: XA}
categories: {cafe: Cafes & Restaurants}
rules:
  - name: bakery
    when: {payee: CRUMB BAKERY}
    category: cafes
"""
    run = start_run(tmp_path, [build_expense("t-1", "2025-11-12", 2.9, "CRUMB BAKERY")], "without-category", config_text=config_with_typo)

    # when
    exit_code = run.run("prepare")

    # then
    assert exit_code == 1
    assert not (run.out / "categorize").exists()


def test_should_name_a_subcategory_with_its_parent_when_the_category_sits_inside_another(tmp_path: Path) -> None:
    # given
    lipstick = build_expense("t-1", "2025-11-03", 14.9, "ROSEWELL BEAUTY", COSMETICS_ID)
    run = start_run(tmp_path, [lipstick], "recheck-all")

    # when
    run.run("prepare")

    # then
    task = run.read_tasks("categorize")[0]
    assert task["categories"]["personal_cosmetics"] == "Personal / Cosmetics"
    assert task["merchants"][0]["transactions"][0]["currentCategory"] == "Personal / Cosmetics"


def test_should_number_the_undecided_rows_after_the_changes_when_the_proposal_holds_both(tmp_path: Path) -> None:
    # given
    tobacco_purchase = build_expense("t-1", "2025-11-10", 12, "SMOKE CORNER NO.4           LINDENPORT     XA")
    unknown_payments = [build_expense(f"t-{day}", f"2025-11-{day:02}", 6, "TOMAS BREK", GROCERIES_ID) for day in (2, 3)]
    run = start_run(tmp_path, [tobacco_purchase, *unknown_payments], "recheck-all")
    run.run("prepare")
    run.answer_every_task("categorize", {f"t-{day}": {"category": None, "confidence": "low", "reason": "a person"} for day in (2, 3)})
    run.run("route")
    run.write_answer("research", "merchant-001.json", {"merchant": "TOMAS BREK", "place": "unknown", "source": None, "trust": "none"})
    run.answer_every_task("rejudge", {f"t-{day}": {"category": None, "confidence": "low", "reason": "a person"} for day in (2, 3)})
    run.run("verify")

    # when
    run.run("propose")

    # then
    proposal_lines = (run.out / "proposal.md").read_text(encoding="utf-8").splitlines()
    assert any(line.startswith("| 1 | 2025-11-10 | SMOKE CORNER NO.4 |") for line in proposal_lines)
    assert "| 2 | 2025-11-02 … 2025-11-03 (×2) | TOMAS BREK | Main Card | -12 EUR |  | Groceries → ? | a person |" in proposal_lines


def test_should_show_1_row_per_currency_when_an_undecided_merchant_is_paid_in_2_currencies(tmp_path: Path) -> None:
    # given
    euro_payment = build_expense("t-1", "2025-11-02", 6, "TOMAS BREK", GROCERIES_ID)
    dollar_payment = build_expense("t-2", "2025-11-03", 7, "TOMAS BREK", GROCERIES_ID, account_id=USD_ID)
    run = start_run(tmp_path, [euro_payment, dollar_payment], "recheck-all")
    run.run("prepare")
    unsearchable_answer = {"category": None, "confidence": "low", "reason": "a person", "searchable": False}
    run.answer_every_task("categorize", {"t-1": unsearchable_answer, "t-2": unsearchable_answer})
    run.run("route")
    run.run("verify")

    # when
    run.run("propose")

    # then
    proposal_lines = (run.out / "proposal.md").read_text(encoding="utf-8").splitlines()
    assert "| 1 | 2025-11-02 | TOMAS BREK | Main Card | -6 EUR |  | Groceries → ? | a person |" in proposal_lines
    assert "| 2 | 2025-11-03 | TOMAS BREK | USD | -7 USD |  | Groceries → ? | a person |" in proposal_lines


def test_should_show_the_likely_category_of_an_undecided_merchant_when_the_agent_names_a_best_guess(tmp_path: Path) -> None:
    # given
    unknown_shop = build_expense("t-1", "2025-11-18", 61.2, "MAPLE THREAD BOUTIQUE", GROCERIES_ID)
    run = start_run(tmp_path, [unknown_shop], "recheck-all")
    run.run("prepare")
    guess_answer = {"category": None, "confidence": "low", "reason": "an unknown shop", "likely": "clothing", "searchable": False}
    run.answer_every_task("categorize", {"t-1": guess_answer})
    run.run("route")
    run.run("verify")

    # when
    run.run("propose")

    # then
    proposal_lines = (run.out / "proposal.md").read_text(encoding="utf-8").splitlines()
    assert "| 1 | 2025-11-18 | MAPLE THREAD BOUTIQUE | Main Card | -61.2 EUR |  | Groceries → Clothing? | an unknown shop |" in proposal_lines
    assert run.read_proposal()["undecided"][0]["likelyCategory"] == "Clothing"


def test_should_show_the_current_category_as_likely_when_the_verifier_rejects_the_change(tmp_path: Path) -> None:
    # given
    clothes_at_hypermarket = build_expense("t-1", "2025-11-10", 42, "HYPERMART EAST", CLOTHING_ID)
    run = start_run(tmp_path, [clothes_at_hypermarket], "recheck-all")
    run.run("prepare")
    run.answer_every_task("categorize", {"t-1": {"category": "groceries", "confidence": "high", "reason": "a supermarket"}})
    run.run("route")
    run.run("verify")
    run.write_answer("verify", "merchant-001.json", [{"id": "t-1", "decision": "reject", "reason": "a hypermarket also sells clothes"}])

    # when
    run.run("propose")

    # then
    proposal_text = (run.out / "proposal.md").read_text(encoding="utf-8")
    assert "| Clothing → Clothing? |" in proposal_text


def test_should_show_2_reasons_and_count_the_rest_when_a_grouped_row_holds_more(tmp_path: Path) -> None:
    # given
    payments = [build_expense(f"t-{day}", f"2025-11-{day:02}", day, "TOMAS BREK", GROCERIES_ID) for day in (2, 3, 4, 5)]
    run = start_run(tmp_path, payments, "recheck-all")
    run.run("prepare")
    run.answer_every_task(
        "categorize",
        {f"t-{day}": {"category": None, "confidence": "low", "reason": f"a person, {day} EUR", "searchable": False} for day in (2, 3, 4, 5)},
    )
    run.run("route")
    run.run("verify")

    # when
    run.run("propose")

    # then
    proposal_text = (run.out / "proposal.md").read_text(encoding="utf-8")
    assert "| a person, 2 EUR; a person, 3 EUR (+2 similar) |" in proposal_text


def test_should_show_the_comment_of_a_confirmed_example_when_the_user_gave_one(tmp_path: Path) -> None:
    # given
    verified_text = (
        f"t-1: {{category: Clothing, category_id: {CLOTHING_ID}, by: user, payee: OUTLET 6227, "
        "reason: user chose the category, comment: Work shoes (Outlet), confirmed: '2025-11-19'}\n"
    )
    run = start_run(tmp_path, [build_expense("t-2", "2025-11-20", 19.9, "OUTLET 6231")], "without-category", verified_text=verified_text)

    # when
    run.run("prepare")

    # then
    assert run.read_tasks("categorize")[0]["confirmedExamples"] == ["OUTLET 6227 → Clothing: user chose the category (Work shoes (Outlet))"]
