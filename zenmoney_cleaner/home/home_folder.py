import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

HOME_VARIABLE = "ZENMONEY_CLEANER_HOME"
_FOLDER_NAME = "zenmoney-cleaner"
_SETTINGS_FILE_NAME = "config.yml"


class MissingHomeError(Exception):
    pass


class HomeSource(Enum):
    OPTION = "the option --home"
    VARIABLE = f"${HOME_VARIABLE}"
    PROJECT = "the project folder"
    USER_ACCOUNT = "your user account"


class HomePlace(Enum):
    PROJECT = "project"
    USER_ACCOUNT = "user-account"


@dataclass(frozen=True)
class HomeFolder:
    path: Path
    source: HomeSource


class HomeFinder:
    def __init__(self, environment: Mapping[str, str], current_folder: Path, platform: str, user_folder: Path) -> None:
        self._environment = environment
        self._current_folder = current_folder
        self._platform = platform
        self._user_folder = user_folder

    @classmethod
    def for_this_process(cls) -> "HomeFinder":
        return cls(os.environ, Path.cwd(), sys.platform, Path.home())

    def find_home(self, option: str | None) -> HomeFolder | None:
        if option:
            return HomeFolder(Path(option).resolve(), HomeSource.OPTION)
        if self._environment.get(HOME_VARIABLE):
            return HomeFolder(Path(self._environment[HOME_VARIABLE]).resolve(), HomeSource.VARIABLE)

        current_folder = self._current_folder.resolve()
        for folder in (current_folder, *current_folder.parents):
            if (folder / _FOLDER_NAME / _SETTINGS_FILE_NAME).exists():
                return HomeFolder(folder / _FOLDER_NAME, HomeSource.PROJECT)

        user_account_path = self.locate(HomePlace.USER_ACCOUNT)
        if (user_account_path / _SETTINGS_FILE_NAME).exists():
            return HomeFolder(user_account_path, HomeSource.USER_ACCOUNT)
        return None

    def locate(self, place: HomePlace) -> Path:
        if place == HomePlace.PROJECT:
            return self._current_folder.resolve() / _FOLDER_NAME

        return self._locate_system_config_folder() / _FOLDER_NAME

    def _locate_system_config_folder(self) -> Path:
        if self._platform == "darwin":
            return self._user_folder / "Library" / "Application Support"
        if self._platform == "win32":
            return Path(self._environment.get("APPDATA") or self._user_folder / "AppData" / "Roaming")

        return Path(self._environment.get("XDG_CONFIG_HOME") or self._user_folder / ".config")
