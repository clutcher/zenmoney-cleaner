import re
from pathlib import Path
from typing import Any

import yaml

from zenmoney_cleaner.settings.settings import (
    CategorizeAction,
    CorrectionSettings,
    DeleteAction,
    Location,
    Rule,
    RuleAction,
    RuleCondition,
    Settings,
    TransferAction,
)
from zenmoney_cleaner.snapshot.transaction import TransactionKind

_CONDITION_KEYS = {"payee", "comment", "account", "type"}
_RULE_KINDS_BY_NAME_MAP = {"expense": TransactionKind.EXPENSE, "income": TransactionKind.INCOME}


class SettingsError(Exception):
    pass


class _Problems:
    def __init__(self, file_name: str) -> None:
        self._file_name = file_name
        self._messages: list[str] = []

    def add(self, place: str, message: str) -> None:
        self._messages.append(f"{self._file_name}, {place}: {message}")

    def raise_if_any(self) -> None:
        if self._messages:
            raise SettingsError("\n".join(self._messages))


def read_settings(path: Path) -> Settings:
    raw = _read_yaml(path)
    problems = _Problems(path.name)

    category_names_by_key_map = {str(key): str(name) for key, name in (raw.get("categories") or {}).items()}
    settings = Settings(
        location=_read_location(raw.get("location") or {}, problems),
        category_names_by_key_map=category_names_by_key_map,
        payee_strip_patterns=tuple(
            _compile(pattern, f"payee.strip[{index}]", problems)
            for index, pattern in enumerate((raw.get("payee") or {}).get("strip") or [])
        ),
        rules=tuple(
            _read_rule(raw_rule, index, category_names_by_key_map, problems)
            for index, raw_rule in enumerate(raw.get("rules") or [])
        ),
        corrections=_read_corrections(raw.get("corrections") or {}),
    )
    problems.raise_if_any()
    return settings


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as yaml_file:
        raw = yaml.safe_load(yaml_file)
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise SettingsError(f"{path.name}: the top level must be a mapping")
    return raw


def _read_location(raw_location: dict[str, Any], problems: _Problems) -> Location:
    for key in ("country", "country_code"):
        if not raw_location.get(key):
            problems.add("location", f"{key} is missing")

    return Location(
        country=str(raw_location.get("country", "")),
        country_code=str(raw_location.get("country_code", "")),
        city=str(raw_location["city"]) if raw_location.get("city") else None,
    )


def _read_rule(raw_rule: dict[str, Any], index: int, category_names_by_key_map: dict[str, str], problems: _Problems) -> Rule:
    name = str(raw_rule.get("name") or f"rules[{index}]")
    place = f"rule {name}"
    return Rule(
        name=name,
        condition=_read_condition(raw_rule.get("when") or {}, place, problems),
        action=_read_action(raw_rule, place, category_names_by_key_map, problems),
    )


def _read_condition(raw_condition: dict[str, Any], place: str, problems: _Problems) -> RuleCondition:
    if not raw_condition:
        problems.add(place, "when is missing or empty, so the rule would match every transaction")
    unknown_keys = set(raw_condition) - _CONDITION_KEYS
    if unknown_keys:
        problems.add(place, f"when holds unknown keys {sorted(unknown_keys)}; allowed are {sorted(_CONDITION_KEYS)}")

    raw_type = raw_condition.get("type")
    if raw_type is not None and raw_type not in _RULE_KINDS_BY_NAME_MAP:
        problems.add(place, f"type {raw_type!r} is neither expense nor income")

    return RuleCondition(
        payees=frozenset(text.lower() for text in _read_texts(raw_condition.get("payee"))),
        comment_fragments=tuple(text.lower() for text in _read_texts(raw_condition.get("comment"))),
        account_name=raw_condition.get("account"),
        kind=_RULE_KINDS_BY_NAME_MAP.get(raw_type) if raw_type is not None else None,
    )


def _read_texts(raw_texts: Any) -> list[str]:
    if raw_texts is None:
        return []
    if isinstance(raw_texts, list):
        return [str(text).strip() for text in raw_texts]
    return [str(raw_texts).strip()]


def _read_action(
    raw_rule: dict[str, Any], place: str, category_names_by_key_map: dict[str, str], problems: _Problems
) -> RuleAction:
    action_name = raw_rule.get("action", "categorize")
    reason = str(raw_rule.get("reason", ""))
    if action_name == "delete":
        return DeleteAction(reason)
    if action_name == "transfer":
        if not raw_rule.get("to_account"):
            problems.add(place, "a transfer rule needs to_account")
        return TransferAction(str(raw_rule.get("to_account", "")), reason)
    if action_name != "categorize":
        problems.add(place, f"action {action_name!r} is none of categorize, delete, transfer")

    return CategorizeAction(
        category_key=_read_category_key(raw_rule.get("category"), place, category_names_by_key_map, problems),
        reason=reason,
    )


def _read_category_key(
    raw_key: Any, place: str, category_names_by_key_map: dict[str, str], problems: _Problems
) -> str:
    if raw_key not in category_names_by_key_map:
        problems.add(place, f"category {raw_key!r} is not a key of categories in config.yml")
    return str(raw_key)


def _read_corrections(raw_corrections: dict[str, Any]) -> CorrectionSettings:
    return CorrectionSettings(
        match_window_days=int(raw_corrections.get("match_window_days", 6)),
        max_match_size=int(raw_corrections.get("max_match_size", 5)),
        adjustment_category_name=str(raw_corrections["adjustment_category"]) if raw_corrections.get("adjustment_category") else None,
    )


def _compile(raw_pattern: Any, place: str, problems: _Problems) -> re.Pattern[str]:
    try:
        return re.compile(str(raw_pattern), re.IGNORECASE)
    except re.error as error:
        problems.add(place, f"pattern {raw_pattern!r} is not a valid regular expression: {error}")
        return re.compile(re.escape(str(raw_pattern)))
