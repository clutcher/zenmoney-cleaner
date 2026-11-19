from dataclasses import dataclass

from zenmoney_cleaner.categorizing.category_catalog import CategoryCatalog
from zenmoney_cleaner.categorizing.judgement import Judgement, Recategorize, Undecided
from zenmoney_cleaner.settings.settings import Confidence

_AGENT_SOURCE = "agent"


class AnswerError(Exception):
    pass


@dataclass(frozen=True)
class AgentAnswer:
    transaction_id: str
    category_key: str | None
    confidence: str
    reason: str
    searchable: bool = True
    likely_category_key: str | None = None


def judge_by_answers(
    answers: list[AgentAnswer], expected_transaction_ids: set[str], catalog: CategoryCatalog
) -> dict[str, Judgement]:
    _check_answers(answers, expected_transaction_ids, catalog)

    return {answer.transaction_id: _judge(answer, catalog) for answer in answers}


def list_unsearchable_transaction_ids(answers: list[AgentAnswer]) -> frozenset[str]:
    return frozenset(answer.transaction_id for answer in answers if not answer.searchable)


def _check_answers(answers: list[AgentAnswer], expected_transaction_ids: set[str], catalog: CategoryCatalog) -> None:
    problems: list[str] = []
    answered_ids = [answer.transaction_id for answer in answers]
    duplicate_ids = sorted({transaction_id for transaction_id in answered_ids if answered_ids.count(transaction_id) > 1})
    missing_ids = sorted(expected_transaction_ids - set(answered_ids))
    unknown_ids = sorted(set(answered_ids) - expected_transaction_ids)
    if duplicate_ids:
        problems.append(f"answered more than once: {duplicate_ids}")
    if missing_ids:
        problems.append(f"not answered: {missing_ids}")
    if unknown_ids:
        problems.append(f"answers for transactions not in the tasks: {unknown_ids}")

    for answer in answers:
        if answer.category_key is not None and not catalog.holds(answer.category_key):
            problems.append(f"{answer.transaction_id}: category {answer.category_key!r} is not a key of the task")
        if answer.likely_category_key is not None and not catalog.holds(answer.likely_category_key):
            problems.append(f"{answer.transaction_id}: likely {answer.likely_category_key!r} is not a key of the task")
        if answer.confidence not in {confidence.value for confidence in Confidence}:
            problems.append(f"{answer.transaction_id}: confidence {answer.confidence!r} is none of high, medium, low")

    if problems:
        raise AnswerError("\n".join(problems))


def _judge(answer: AgentAnswer, catalog: CategoryCatalog) -> Judgement:
    if answer.category_key is None:
        likely_category_name = catalog.get_category(answer.likely_category_key).full_name if answer.likely_category_key else None
        return Undecided(answer.reason, likely_category_name)

    return Recategorize(catalog.get_category(answer.category_key), Confidence(answer.confidence), answer.reason, _AGENT_SOURCE)
