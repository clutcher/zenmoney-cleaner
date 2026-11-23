from dataclasses import dataclass

from zenmoney_cleaner.snapshot.transaction import Transaction

_EXAMPLE_LIMIT = 300


@dataclass(frozen=True)
class VerifiedEntry:
    transaction_id: str
    category_id: str
    category_name: str
    payee: str
    reason: str
    confirmed_on: str
    comment: str | None = None


@dataclass(frozen=True)
class ConfirmedExample:
    payee: str
    category_name: str
    reason: str
    comment: str | None = None

    def describe(self) -> str:
        if not self.comment:
            return f"{self.payee} → {self.category_name}: {self.reason}"

        return f"{self.payee} → {self.category_name}: {self.reason} ({self.comment})"


@dataclass(frozen=True)
class VerifiedTransactions:
    entries_by_transaction_id_map: dict[str, VerifiedEntry]

    def confirms(self, transaction: Transaction) -> bool:
        if transaction.id not in self.entries_by_transaction_id_map:
            return False

        return self.entries_by_transaction_id_map[transaction.id].category_id == transaction.category_id

    def list_examples(self) -> tuple[ConfirmedExample, ...]:
        newest_entries = sorted(self.entries_by_transaction_id_map.values(), key=lambda entry: entry.confirmed_on, reverse=True)
        examples_by_payee_and_category_map: dict[tuple[str, str], ConfirmedExample] = {}
        for entry in newest_entries:
            example_key = (entry.payee.upper(), entry.category_name)
            if example_key not in examples_by_payee_and_category_map:
                examples_by_payee_and_category_map[example_key] = ConfirmedExample(entry.payee, entry.category_name, entry.reason, entry.comment)

        return tuple(examples_by_payee_and_category_map.values())[:_EXAMPLE_LIMIT]
