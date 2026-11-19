from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import combinations

from zenmoney_cleaner.settings.settings import CorrectionSettings
from zenmoney_cleaner.snapshot.snapshot import Snapshot
from zenmoney_cleaner.snapshot.transaction import Transaction

_CENTS_PER_UNIT = 100
_PENDING_DAYS = 7
_MATCH_LIMIT = 5
_ROUNDING_CENTS = 1
_CANDIDATE_LIMIT = 5


@dataclass(frozen=True)
class ClosedChain:
    account_name: str
    corrections: tuple[Transaction, ...]


@dataclass(frozen=True)
class CorrectionMatch:
    correction: Transaction
    transaction_sets: tuple[tuple[Transaction, ...], ...]


@dataclass(frozen=True)
class OpenChain:
    account_name: str
    corrections: tuple[Transaction, ...]
    residual: float
    is_pending: bool
    matches: tuple[CorrectionMatch, ...]
    suspects: tuple[Transaction, ...]


@dataclass(frozen=True)
class CorrectionReport:
    closed_chains: tuple[ClosedChain, ...]
    open_chains: tuple[OpenChain, ...]


class MissingAdjustmentCategoryError(Exception):
    pass


def find_correction_chains(snapshot: Snapshot, settings: CorrectionSettings) -> CorrectionReport:
    if snapshot.balance_adjustment_category_id is None:
        raise MissingAdjustmentCategoryError(
            "Zenmoney reports no balance-adjustment category, which happens when it is missing or 2 categories share its name; "
            "name it as corrections.adjustment_category in config.yml. "
            f"Categories whose transactions are mostly synced with no payee: {_describe_adjustment_candidates(snapshot) or 'none'}"
        )

    corrections_by_account_id_map: dict[str, list[Transaction]] = defaultdict(list)
    for transaction in snapshot.transactions:
        if transaction.is_auto_correction():
            corrections_by_account_id_map[transaction.account_id].append(transaction)

    newest_day = max((transaction.date for transaction in snapshot.transactions), default=date.min)
    closed_chains: list[ClosedChain] = []
    open_chains: list[OpenChain] = []
    for account_id, corrections in corrections_by_account_id_map.items():
        account_name = snapshot.get_account(account_id).name
        chains, open_corrections = _split_into_chains(sorted(corrections, key=lambda correction: (correction.date, correction.id)))
        closed_chains += [ClosedChain(account_name, chain) for chain in chains]
        if open_corrections:
            account_transactions = [
                transaction
                for transaction in snapshot.transactions
                if transaction.account_id == account_id and not transaction.is_auto_correction()
            ]
            open_chains.append(_describe_open_chain(account_name, open_corrections, account_transactions, settings, newest_day))

    return CorrectionReport(tuple(closed_chains), tuple(open_chains))


def _describe_adjustment_candidates(snapshot: Snapshot) -> str:
    transactions_by_category_name_map: dict[str, list[Transaction]] = defaultdict(list)
    for transaction in snapshot.transactions:
        if transaction.category_name is not None:
            transactions_by_category_name_map[transaction.category_name].append(transaction)

    candidate_counts = []
    for category_name, transactions in transactions_by_category_name_map.items():
        correction_like_count = sum(1 for transaction in transactions if transaction.is_synced_without_payee())
        if correction_like_count * 2 > len(transactions):
            candidate_counts.append((category_name, correction_like_count, len(transactions)))
    candidate_counts.sort(key=lambda candidate: -candidate[1])
    return ", ".join(f"{name} ({count} of {total})" for name, count, total in candidate_counts[:_CANDIDATE_LIMIT])


def _split_into_chains(corrections: list[Transaction]) -> tuple[list[tuple[Transaction, ...]], tuple[Transaction, ...]]:
    chains: list[tuple[Transaction, ...]] = []
    open_corrections = list(corrections)
    while (chain_bounds := _find_shortest_zero_run(open_corrections)) is not None:
        start, end = chain_bounds
        chains.append(tuple(open_corrections[start:end]))
        del open_corrections[start:end]
    return sorted(chains, key=lambda chain: chain[0].date), tuple(open_corrections)


def _find_shortest_zero_run(corrections: list[Transaction]) -> tuple[int, int] | None:
    for length in range(2, len(corrections) + 1):
        for start in range(len(corrections) - length + 1):
            run_cents = sum(_to_cents(correction.signed_amount()) for correction in corrections[start : start + length])
            if abs(run_cents) <= _ROUNDING_CENTS:
                return start, start + length
    return None


def _describe_open_chain(
    account_name: str,
    corrections: tuple[Transaction, ...],
    account_transactions: list[Transaction],
    settings: CorrectionSettings,
    newest_day: date,
) -> OpenChain:
    residual = round(sum(correction.signed_amount() for correction in corrections), 2)
    suspects = tuple(
        transaction for transaction in account_transactions if _to_cents(abs(transaction.amount)) == _to_cents(abs(residual))
    )
    return OpenChain(
        account_name=account_name,
        corrections=corrections,
        residual=residual,
        is_pending=newest_day - corrections[-1].date <= timedelta(days=_PENDING_DAYS),
        matches=tuple(_match(correction, account_transactions, settings) for correction in corrections),
        suspects=suspects,
    )


def _match(correction: Transaction, account_transactions: list[Transaction], settings: CorrectionSettings) -> CorrectionMatch:
    window_start = correction.date - timedelta(days=settings.match_window_days)
    candidates = [transaction for transaction in account_transactions if window_start <= transaction.date <= correction.date]
    target_cents = _to_cents(correction.signed_amount())

    transaction_sets: list[tuple[Transaction, ...]] = []
    for size in range(1, settings.max_match_size + 1):
        for candidate_set in combinations(candidates, size):
            if sum(_to_cents(transaction.signed_amount()) for transaction in candidate_set) == target_cents:
                transaction_sets.append(candidate_set)
                if len(transaction_sets) == _MATCH_LIMIT:
                    return CorrectionMatch(correction, tuple(transaction_sets))
    return CorrectionMatch(correction, tuple(transaction_sets))


def _to_cents(amount: float) -> int:
    return round(amount * _CENTS_PER_UNIT)
