from dataclasses import dataclass, replace

from zenmoney_cleaner.snapshot.transaction import Transaction


@dataclass(frozen=True)
class Category:
    id: str
    name: str
    parent_id: str | None
    parent_name: str | None = None

    @property
    def full_name(self) -> str:
        if self.parent_name is None:
            return self.name

        return f"{self.parent_name} / {self.name}"


@dataclass(frozen=True)
class Account:
    id: str
    name: str
    instrument: str


@dataclass(frozen=True)
class Snapshot:
    transactions: tuple[Transaction, ...]
    categories: tuple[Category, ...]
    accounts: tuple[Account, ...]
    balance_adjustment_category_id: str | None

    def with_balance_adjustment_category(self, category_id: str | None) -> "Snapshot":
        transactions = tuple(
            replace(transaction, is_balance_adjustment=category_id is not None and transaction.category_id == category_id)
            for transaction in self.transactions
        )
        return replace(self, transactions=transactions, balance_adjustment_category_id=category_id)

    def find_category(self, name: str) -> Category | None:
        category_by_full_name = next((category for category in self.categories if category.full_name == name), None)
        if category_by_full_name is not None:
            return category_by_full_name

        return next((category for category in self.categories if category.name == name), None)

    def find_account(self, name: str) -> Account | None:
        return next((account for account in self.accounts if account.name == name), None)

    def get_account(self, account_id: str) -> Account:
        return next(account for account in self.accounts if account.id == account_id)
