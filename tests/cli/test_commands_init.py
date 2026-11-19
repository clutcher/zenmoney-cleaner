import json
from pathlib import Path

import pytest
import yaml

from tests.support.categorizing_run import start_run
from tests.support.zenmoney_responses import CATEGORIES_RESPONSE, COSMETICS_ID, build_expense
from zenmoney_cleaner.cli.commands import main


def _init(linux_user: Path, *options: str) -> int:
    categories_path = linux_user / "categories.json"
    categories_path.write_text(json.dumps(CATEGORIES_RESPONSE), encoding="utf-8")
    return main(["init", "--place", "user-account", "--categories", str(categories_path), "--country", "Examplia", "--country-code", "XA", *options])


def test_should_write_a_key_for_every_category_but_the_adjustment_when_the_home_is_set_up(linux_user: Path) -> None:
    # when
    exit_code = _init(linux_user, "--city", "Lindenport")

    # then
    home = linux_user / "config" / "zenmoney-cleaner"
    raw_settings = yaml.safe_load((home / "config.yml").read_text(encoding="utf-8"))
    assert exit_code == 0
    assert raw_settings["location"] == {"country": "Examplia", "country_code": "XA", "city": "Lindenport"}
    assert raw_settings["categories"] == {
        "cafes_restaurants": "Cafes & Restaurants",
        "groceries": "Groceries",
        "clothing": "Clothing",
        "personal": "Personal",
        "personal_cosmetics": "Personal / Cosmetics",
    }
    assert (home / "policy.md").read_text(encoding="utf-8").startswith("# How I categorize")


def test_should_judge_a_subcategory_by_its_full_name_when_a_run_uses_the_written_settings(linux_user: Path) -> None:
    # given
    _init(linux_user)
    settings_text = (linux_user / "config" / "zenmoney-cleaner" / "config.yml").read_text(encoding="utf-8")
    lipstick = build_expense("t-1", "2025-11-03", 14.9, "ROSEWELL BEAUTY", COSMETICS_ID)
    run = start_run(linux_user / "run", [lipstick], "recheck-all", config_text=settings_text)

    # when
    exit_code = run.run("prepare")

    # then
    assert exit_code == 0
    assert run.read_tasks("categorize")[0]["categories"]["personal_cosmetics"] == "Personal / Cosmetics"


def test_should_refuse_the_setup_when_the_home_holds_a_config_already(linux_user: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # given
    _init(linux_user)
    settings_path = linux_user / "config" / "zenmoney-cleaner" / "config.yml"
    settings_path.write_text("location: {country: Otherland, country_code: XB}\n", encoding="utf-8")

    # when
    exit_code = _init(linux_user)

    # then
    assert exit_code == 1
    assert "Otherland" in settings_path.read_text(encoding="utf-8")
