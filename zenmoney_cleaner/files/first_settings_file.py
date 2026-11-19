import re
import shutil
from pathlib import Path

import yaml

from zenmoney_cleaner.settings.settings import Location

_HEADER_TEXT = (
    "# Settings of zenmoney-cleaner, made by its setup from your Zenmoney categories.\n"
    "# docs/configuration.md of the plugin explains each key; ask Claude to change any of them.\n"
    "# Remove the categories that the agents must never pick.\n\n"
)
_GENERIC_PAYEE_STRIP_PATTERNS = (r"\s{2,}[A-Z .]+$", r"^(MP\*\*|SUMUP\s*\*|SQ \*)", r"\s+\d{2,}$")


class HomeAlreadySetUpError(Exception):
    pass


def write_first_settings(home: Path, location: Location, category_names_by_key_map: dict[str, str], example_folder: Path) -> None:
    settings_path = home / "config.yml"
    if settings_path.exists():
        raise HomeAlreadySetUpError(f"{settings_path} exists already; change it instead of setting up again")

    home.mkdir(parents=True, exist_ok=True)
    raw_settings = {
        "location": {key: value for key, value in vars(location).items() if value is not None},
        "categories": category_names_by_key_map,
        "payee": {"strip": [rf"\s+{re.escape(location.country_code)}$", *_GENERIC_PAYEE_STRIP_PATTERNS]},
        "rules": [],
    }
    settings_path.write_text(_HEADER_TEXT + yaml.safe_dump(raw_settings, allow_unicode=True, sort_keys=False), encoding="utf-8")

    policy_path = home / "policy.md"
    if not policy_path.exists():
        shutil.copyfile(example_folder / "policy.md", policy_path)
