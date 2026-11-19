from collections import Counter, defaultdict
from dataclasses import dataclass
from statistics import median

from zenmoney_cleaner.payee.merchant_key import MerchantKeyMaker
from zenmoney_cleaner.snapshot.snapshot import Snapshot
from zenmoney_cleaner.snapshot.transaction import Transaction

_TASK_TRANSACTION_LIMIT = 120
_RECURRING_MONTH_COUNT = 3


@dataclass(frozen=True)
class MerchantHabit:
    payment_count: int
    month_count: int
    usual_amount: float
    is_monthly_same_amount: bool


@dataclass(frozen=True)
class MerchantGroup:
    merchant_key: str | None
    transactions: tuple[Transaction, ...]
    habit: MerchantHabit | None
    other_category_counts_by_name_map: dict[str, int]

    def list_transaction_ids(self) -> set[str]:
        return {transaction.id for transaction in self.transactions}


@dataclass(frozen=True)
class CategoryTask:
    number: int
    merchant_groups: tuple[MerchantGroup, ...]


def group_by_merchant(transactions: list[Transaction], snapshot: Snapshot, key_maker: MerchantKeyMaker) -> tuple[MerchantGroup, ...]:
    transactions_by_merchant_key_map: dict[str | None, list[Transaction]] = defaultdict(list)
    for transaction in transactions:
        transactions_by_merchant_key_map[key_maker.make_key(transaction.payee)].append(transaction)

    snapshot_transactions_by_merchant_key_map: dict[str | None, list[Transaction]] = defaultdict(list)
    for transaction in snapshot.transactions:
        if transaction.is_categorizable():
            snapshot_transactions_by_merchant_key_map[key_maker.make_key(transaction.payee)].append(transaction)

    grouped_ids = {transaction.id for transaction in transactions}
    return tuple(
        MerchantGroup(
            merchant_key=merchant_key,
            transactions=tuple(merchant_transactions),
            habit=_describe_habit(snapshot_transactions_by_merchant_key_map[merchant_key]) if merchant_key else None,
            other_category_counts_by_name_map=dict(Counter(
                transaction.category_name
                for transaction in snapshot_transactions_by_merchant_key_map[merchant_key]
                if transaction.id not in grouped_ids and transaction.category_name
            )),
        )
        for merchant_key, merchant_transactions in transactions_by_merchant_key_map.items()
    )


def split_into_tasks(merchant_groups: tuple[MerchantGroup, ...]) -> tuple[CategoryTask, ...]:
    tasks: list[list[MerchantGroup]] = [[]]
    task_transaction_count = 0
    for merchant_group in sorted(merchant_groups, key=lambda group: group.merchant_key or ""):
        if tasks[-1] and task_transaction_count + len(merchant_group.transactions) > _TASK_TRANSACTION_LIMIT:
            tasks.append([])
            task_transaction_count = 0
        tasks[-1].append(merchant_group)
        task_transaction_count += len(merchant_group.transactions)

    return tuple(CategoryTask(number, tuple(groups)) for number, groups in enumerate(tasks, start=1) if groups)


def _describe_habit(merchant_transactions: list[Transaction]) -> MerchantHabit:
    months_by_amount_map: dict[float, set[str]] = defaultdict(set)
    for transaction in merchant_transactions:
        months_by_amount_map[round(transaction.amount, 2)].add(transaction.date.strftime("%Y-%m"))

    month_count = len({transaction.date.strftime("%Y-%m") for transaction in merchant_transactions})
    most_months_of_1_amount = max((len(months) for months in months_by_amount_map.values()), default=0)
    return MerchantHabit(
        payment_count=len(merchant_transactions),
        month_count=month_count,
        usual_amount=round(median(transaction.amount for transaction in merchant_transactions), 2),
        is_monthly_same_amount=most_months_of_1_amount >= _RECURRING_MONTH_COUNT,
    )
