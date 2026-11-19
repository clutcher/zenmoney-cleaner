from collections import defaultdict
from dataclasses import dataclass
from enum import Enum

from zenmoney_cleaner.categorizing.categorizing_scope import CategorizingScope
from zenmoney_cleaner.categorizing.category_tasks import MerchantGroup, group_by_merchant
from zenmoney_cleaner.categorizing.judgement import Change, Judgement, Recategorize, Undecided
from zenmoney_cleaner.categorizing.rule_categorizer import RuleCategorizer
from zenmoney_cleaner.categorizing.verified_transactions import VerifiedTransactions
from zenmoney_cleaner.payee.merchant_key import MerchantKeyMaker
from zenmoney_cleaner.settings.settings import Confidence
from zenmoney_cleaner.snapshot.snapshot import Snapshot
from zenmoney_cleaner.snapshot.transaction import Transaction


class Verdict(Enum):
    KEEP = "keep"
    REJECT = "reject"


@dataclass(frozen=True)
class RuleJudgement:
    transaction: Transaction
    merchant_key: str | None
    change: Change


@dataclass(frozen=True)
class CategorySelection:
    rule_judgements: tuple[RuleJudgement, ...]
    merchant_groups: tuple[MerchantGroup, ...]

    def list_agent_transaction_ids(self) -> set[str]:
        return {transaction.id for group in self.merchant_groups for transaction in group.transactions}


@dataclass(frozen=True)
class ChangeToVerify:
    transaction: Transaction
    proposal: Recategorize


@dataclass(frozen=True)
class MerchantChanges:
    merchant_group: MerchantGroup
    changes: tuple[ChangeToVerify, ...]


@dataclass(frozen=True)
class VerifierRuling:
    verdict: Verdict
    reason: str


@dataclass(frozen=True)
class ProposedChange:
    transaction: Transaction
    merchant_key: str | None
    change: Change


@dataclass(frozen=True)
class Agreement:
    transaction: Transaction
    merchant_key: str | None
    evidence: Recategorize


@dataclass(frozen=True)
class UndecidedTransaction:
    transaction: Transaction
    judgement: Undecided


@dataclass(frozen=True)
class UnknownMerchant:
    merchant_key: str | None
    undecided_transactions: tuple[UndecidedTransaction, ...]

    @property
    def transactions(self) -> tuple[Transaction, ...]:
        return tuple(undecided.transaction for undecided in self.undecided_transactions)

    @property
    def reasons(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(undecided.judgement.reason for undecided in self.undecided_transactions))


@dataclass(frozen=True)
class CategoryProposal:
    scope: CategorizingScope
    changes: tuple[ProposedChange, ...]
    agreements: tuple[Agreement, ...]
    unknown_merchants: tuple[UnknownMerchant, ...]


def select_for_categorizing(
    snapshot: Snapshot,
    rule_categorizer: RuleCategorizer,
    key_maker: MerchantKeyMaker,
    verified_transactions: VerifiedTransactions,
    scope: CategorizingScope,
) -> CategorySelection:
    rule_judgements: list[RuleJudgement] = []
    agent_transactions: list[Transaction] = []
    for transaction in _select_transactions(snapshot, verified_transactions, scope):
        merchant_key = key_maker.make_key(transaction.payee)
        change = rule_categorizer.judge(transaction, merchant_key)
        if change is None:
            agent_transactions.append(transaction)
        else:
            rule_judgements.append(RuleJudgement(transaction, merchant_key, change))

    return CategorySelection(tuple(rule_judgements), group_by_merchant(agent_transactions, snapshot, key_maker))


def select_merchants_to_research(
    selection: CategorySelection, first_judgements_by_transaction_id_map: dict[str, Judgement], unsearchable_transaction_ids: frozenset[str]
) -> tuple[MerchantGroup, ...]:
    merchant_groups: list[MerchantGroup] = []
    for group in selection.merchant_groups:
        unsure_ids = {
            transaction.id
            for transaction in group.transactions
            if _needs_research(transaction, first_judgements_by_transaction_id_map[transaction.id])
        }
        if unsure_ids and not unsure_ids <= unsearchable_transaction_ids:
            merchant_groups.append(group)
    return tuple(merchant_groups)


def select_changes_to_verify(
    selection: CategorySelection, judgements_by_transaction_id_map: dict[str, Judgement]
) -> tuple[MerchantChanges, ...]:
    merchant_changes: list[MerchantChanges] = []
    for group in selection.merchant_groups:
        changes = tuple(
            ChangeToVerify(transaction, judgements_by_transaction_id_map[transaction.id])
            for transaction in group.transactions
            if _overrides_user_category(transaction, judgements_by_transaction_id_map[transaction.id])
        )
        if changes:
            merchant_changes.append(MerchantChanges(group, changes))
    return tuple(merchant_changes)


def propose_categories(
    selection: CategorySelection,
    judgements_by_transaction_id_map: dict[str, Judgement],
    rulings_by_transaction_id_map: dict[str, VerifierRuling],
    scope: CategorizingScope,
) -> CategoryProposal:
    judged_transactions = [(judgement.transaction, judgement.merchant_key, judgement.change) for judgement in selection.rule_judgements] + [
        (transaction, group.merchant_key, _apply_ruling(transaction, judgements_by_transaction_id_map[transaction.id], rulings_by_transaction_id_map.get(transaction.id)))
        for group in selection.merchant_groups
        for transaction in group.transactions
    ]

    changes: list[ProposedChange] = []
    agreements: list[Agreement] = []
    undecided_by_merchant_key_map: dict[str | None, list[UndecidedTransaction]] = defaultdict(list)
    for transaction, merchant_key, judgement in judged_transactions:
        if isinstance(judgement, Undecided):
            undecided_by_merchant_key_map[merchant_key].append(UndecidedTransaction(transaction, judgement))
        elif isinstance(judgement, Recategorize) and judgement.confidence == Confidence.LOW and transaction.has_category():
            guess = Undecided(f"guess only: {judgement.reason}", judgement.category.full_name)
            undecided_by_merchant_key_map[merchant_key].append(UndecidedTransaction(transaction, guess))
        elif isinstance(judgement, Recategorize) and judgement.category.id == transaction.category_id:
            agreements.append(Agreement(transaction, merchant_key, judgement))
        else:
            changes.append(ProposedChange(transaction, merchant_key, judgement))

    unknown_merchants = tuple(
        UnknownMerchant(merchant_key, tuple(undecided_transactions)) for merchant_key, undecided_transactions in undecided_by_merchant_key_map.items()
    )
    return CategoryProposal(scope, tuple(changes), tuple(agreements), unknown_merchants)


def _select_transactions(snapshot: Snapshot, verified_transactions: VerifiedTransactions, scope: CategorizingScope) -> list[Transaction]:
    return [
        transaction
        for transaction in snapshot.transactions
        if transaction.is_categorizable() and scope.covers(transaction) and not verified_transactions.confirms(transaction)
    ]


def _needs_research(transaction: Transaction, judgement: Judgement) -> bool:
    if not isinstance(judgement, Recategorize):
        return True
    if judgement.confidence == Confidence.HIGH:
        return False

    agrees_with_user = judgement.category.id == transaction.category_id
    return judgement.confidence == Confidence.LOW or not agrees_with_user


def _overrides_user_category(transaction: Transaction, judgement: Judgement) -> bool:
    if not transaction.has_category() or not isinstance(judgement, Recategorize):
        return False

    return judgement.category.id != transaction.category_id and judgement.confidence != Confidence.LOW


def _apply_ruling(transaction: Transaction, judgement: Judgement, ruling: VerifierRuling | None) -> Judgement:
    if ruling is None or ruling.verdict == Verdict.KEEP:
        return judgement

    rejected_text = judgement.category.full_name if isinstance(judgement, Recategorize) else "the change"
    return Undecided(f"the verifier rejected {rejected_text}: {ruling.reason}", transaction.category_name)
