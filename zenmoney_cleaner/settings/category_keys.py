import re

from zenmoney_cleaner.snapshot.snapshot import Category

_FALLBACK_KEY = "category"


def make_category_names_by_key_map(categories: tuple[Category, ...], excluded_category_id: str | None) -> dict[str, str]:
    category_names_by_key_map: dict[str, str] = {}
    for category in categories:
        if category.id == excluded_category_id:
            continue
        key = _make_free_key(_make_key(category.full_name), category_names_by_key_map)
        category_names_by_key_map[key] = category.full_name
    return category_names_by_key_map


def _make_key(full_name: str) -> str:
    return "_".join(re.findall(r"\w+", full_name.lower())) or _FALLBACK_KEY


def _make_free_key(key: str, category_names_by_key_map: dict[str, str]) -> str:
    if key not in category_names_by_key_map:
        return key

    number = 2
    while f"{key}_{number}" in category_names_by_key_map:
        number += 1
    return f"{key}_{number}"
