from zenmoney_cleaner.snapshot.snapshot import Category, Snapshot


class UnknownCategoryError(Exception):
    pass


class CategoryCatalog:
    def __init__(self, categories_by_key_map: dict[str, Category]) -> None:
        self._categories_by_key_map = categories_by_key_map

    @classmethod
    def resolve(cls, category_names_by_key_map: dict[str, str], snapshot: Snapshot) -> "CategoryCatalog":
        missing_names = [name for name in category_names_by_key_map.values() if snapshot.find_category(name) is None]
        if missing_names:
            raise UnknownCategoryError(f"config.yml names categories that Zenmoney does not have: {missing_names}")

        categories_by_key_map = {
            key: snapshot.find_category(name) for key, name in category_names_by_key_map.items()
        }
        return cls(categories_by_key_map)

    def describe_categories(self) -> dict[str, str]:
        return {key: category.full_name for key, category in self._categories_by_key_map.items()}

    def list_keys(self) -> list[str]:
        return list(self._categories_by_key_map)

    def holds(self, key: str) -> bool:
        return key in self._categories_by_key_map

    def get_category(self, key: str) -> Category:
        return self._categories_by_key_map[key]
