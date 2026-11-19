from dataclasses import dataclass


@dataclass(frozen=True)
class KnownPlace:
    merchant_key: str
    place: str
    source: str | None
    trust: str
    researched_on: str


@dataclass(frozen=True)
class KnownPlaces:
    places_by_merchant_key_map: dict[str, KnownPlace]

    @classmethod
    def none(cls) -> "KnownPlaces":
        return cls({})

    def knows(self, merchant_key: str | None) -> bool:
        return merchant_key in self.places_by_merchant_key_map

    def get_place(self, merchant_key: str) -> KnownPlace:
        return self.places_by_merchant_key_map[merchant_key]
