import sys
from pathlib import Path

import pytest


@pytest.fixture
def linux_user(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    project_folder = tmp_path / "project"
    project_folder.mkdir()
    monkeypatch.chdir(project_folder)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("ZENMONEY_CLEANER_HOME", raising=False)
    return tmp_path
