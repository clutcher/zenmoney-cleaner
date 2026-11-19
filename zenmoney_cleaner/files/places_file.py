from pathlib import Path
from typing import Any

import yaml

from zenmoney_cleaner.categorizing.known_places import KnownPlace, KnownPlaces


def read_known_places(path: Path) -> KnownPlaces:
    return KnownPlaces({
        merchant_key: KnownPlace(
            merchant_key=merchant_key,
            place=str(raw_place.get("place") or ""),
            source=raw_place.get("source"),
            trust=str(raw_place.get("trust") or "none"),
            researched_on=str(raw_place.get("researched", "")),
        )
        for merchant_key, raw_place in _read_places(path).items()
    })


def record_places(path: Path, places: tuple[KnownPlace, ...]) -> None:
    raw_places = _read_places(path)
    for known_place in places:
        raw_places[known_place.merchant_key] = {
            "place": known_place.place,
            "source": known_place.source,
            "trust": known_place.trust,
            "researched": known_place.researched_on,
        }

    path.write_text(yaml.safe_dump(raw_places, allow_unicode=True, sort_keys=True), encoding="utf-8")


def _read_places(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}

    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
