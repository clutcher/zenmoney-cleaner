from pathlib import Path

import pytest

from zenmoney_cleaner.cli.commands import main


def _create_home(path: Path) -> Path:
    path.mkdir(parents=True)
    (path / "config.yml").write_text("location: {country: Examplia, country_code: XA}\n", encoding="utf-8")
    return path


def test_should_find_the_project_folder_before_the_user_account_when_both_hold_a_config(
    linux_user: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given
    project_home = _create_home(linux_user / "project" / "zenmoney-cleaner")
    _create_home(linux_user / "config" / "zenmoney-cleaner")

    # when
    main(["home"])

    # then
    assert capsys.readouterr().out == f"home: {project_home} (found through this folder)\n"


def test_should_find_the_user_account_folder_when_the_project_has_none(linux_user: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # given
    user_home = _create_home(linux_user / "config" / "zenmoney-cleaner")

    # when
    main(["home"])

    # then
    assert capsys.readouterr().out == f"home: {user_home} (found through your user account)\n"


def test_should_take_the_variable_before_the_folders_when_it_is_set(
    linux_user: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # given
    _create_home(linux_user / "project" / "zenmoney-cleaner")
    chosen_home = linux_user / "chosen"
    monkeypatch.setenv("ZENMONEY_CLEANER_HOME", str(chosen_home))

    # when
    main(["home"])

    # then
    assert capsys.readouterr().out == f"home: {chosen_home} (found through $ZENMONEY_CLEANER_HOME)\n"


def test_should_name_both_places_when_no_home_is_found(linux_user: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # when
    main(["home"])

    # then
    assert capsys.readouterr().out.splitlines() == [
        "home: none found; the setup skill creates 1 of these:",
        f"project: {linux_user / 'project' / 'zenmoney-cleaner'} (this folder only)",
        f"user-account: {linux_user / 'config' / 'zenmoney-cleaner'} (works from any folder)",
    ]


def test_should_stop_a_command_with_an_error_when_no_home_is_found(linux_user: Path) -> None:
    # when
    exit_code = main(["approve", "--proposal", str(linux_user / "proposal.json"), "--out", str(linux_user / "batches.json")])

    # then
    assert exit_code == 1
    assert not (linux_user / "batches.json").exists()
