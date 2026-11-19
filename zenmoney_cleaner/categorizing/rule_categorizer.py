from zenmoney_cleaner.categorizing.category_catalog import CategoryCatalog
from zenmoney_cleaner.categorizing.judgement import Change, ConvertToTransfer, Delete, Recategorize
from zenmoney_cleaner.settings.settings import CategorizeAction, Confidence, DeleteAction, Rule, Settings
from zenmoney_cleaner.snapshot.snapshot import Snapshot
from zenmoney_cleaner.snapshot.transaction import Transaction


class TransferTargetError(Exception):
    pass


class RuleCategorizer:
    def __init__(self, settings: Settings, catalog: CategoryCatalog, snapshot: Snapshot) -> None:
        self._settings = settings
        self._catalog = catalog
        self._snapshot = snapshot

    def judge(self, transaction: Transaction, merchant_key: str | None) -> Change | None:
        rule = self._settings.find_rule(transaction, merchant_key)
        if rule is None:
            return None

        source = f"rule {rule.name}"
        action = rule.action
        if isinstance(action, CategorizeAction):
            return Recategorize(self._catalog.get_category(action.category_key), Confidence.HIGH, action.reason, source)
        if isinstance(action, DeleteAction):
            return Delete(action.reason, source)

        return self._convert_to_transfer(rule, transaction, source)

    def _convert_to_transfer(self, rule: Rule, transaction: Transaction, source: str) -> ConvertToTransfer:
        action = rule.action
        to_account = self._snapshot.find_account(action.to_account_name)
        if to_account is None:
            raise TransferTargetError(f"rule {rule.name} names account {action.to_account_name!r}, which Zenmoney does not have")

        from_account = self._snapshot.get_account(transaction.account_id)
        if to_account.instrument != from_account.instrument:
            raise TransferTargetError(
                f"rule {rule.name} moves {from_account.instrument} from {from_account.name} into {to_account.name}, "
                f"which holds {to_account.instrument}"
            )

        return ConvertToTransfer(to_account, action.reason, source)
