import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from zenmoney_cleaner.categorizing.agent_answers import AgentAnswer, AnswerError
from zenmoney_cleaner.categorizing.category_proposal import MerchantChanges, Verdict, VerifierRuling
from zenmoney_cleaner.categorizing.category_tasks import CategoryTask, MerchantGroup, MerchantHabit
from zenmoney_cleaner.categorizing.known_places import KnownPlace, KnownPlaces
from zenmoney_cleaner.categorizing.verified_transactions import ConfirmedExample
from zenmoney_cleaner.settings.settings import Confidence, Settings
from zenmoney_cleaner.snapshot.transaction import Transaction

CATEGORIZE_STAGE = "categorize"
RESEARCH_STAGE = "research"
REJUDGE_STAGE = "rejudge"
VERIFY_STAGE = "verify"

_JOBS_FILE_NAME = "jobs.workflow.js"
_RERUN_JOBS_FILE_NAME = "jobs-again.workflow.js"
_RERUN_LIMIT = 2


@dataclass(frozen=True)
class TaskContext:
    settings: Settings
    category_full_names_by_key_map: dict[str, str]
    mode: str
    policy_path: Path
    examples: tuple[ConfirmedExample, ...]


@dataclass(frozen=True)
class FaultyTask:
    task_path: Path
    answer_path: Path
    problems: tuple[str, ...]


@dataclass(frozen=True)
class JobStep:
    agent: str
    task_path: Path
    answer_path: Path
    label: str


def write_categorize_jobs(tasks: tuple[CategoryTask, ...], context: TaskContext, directory: Path) -> None:
    _clear_stages(directory, CATEGORIZE_STAGE, RESEARCH_STAGE, REJUDGE_STAGE, VERIFY_STAGE)
    steps = [
        _write_task(
            directory,
            CATEGORIZE_STAGE,
            f"task-{task.number:03}",
            "categorizer",
            _build_categorize_task(task.merchant_groups, context),
        )
        for task in tasks
    ]
    _write_jobs(directory, CATEGORIZE_STAGE, [[step] for step in steps])


def write_research_jobs(
    merchant_groups: tuple[MerchantGroup, ...], known_places: KnownPlaces, context: TaskContext, directory: Path
) -> None:
    _clear_stages(directory, RESEARCH_STAGE, REJUDGE_STAGE, VERIFY_STAGE)
    jobs: list[list[JobStep]] = []
    for index, group in enumerate(merchant_groups, start=1):
        name = f"merchant-{index:03}"
        research_step = _write_task(directory, RESEARCH_STAGE, name, "researcher", _build_research_task(group, context))
        rejudge_task = _build_categorize_task((group,), context) | {"research": str(research_step.answer_path)}
        rejudge_step = _write_task(directory, REJUDGE_STAGE, name, "categorizer", rejudge_task)
        if known_places.knows(group.merchant_key):
            _write_known_place(known_places.get_place(group.merchant_key), research_step.answer_path)
            jobs.append([rejudge_step])
        else:
            jobs.append([research_step, rejudge_step])
    _write_jobs(directory, RESEARCH_STAGE, jobs)


def write_verify_jobs(merchant_changes: tuple[MerchantChanges, ...], context: TaskContext, directory: Path) -> None:
    _clear_stages(directory, VERIFY_STAGE)
    steps = [
        _write_task(directory, VERIFY_STAGE, f"merchant-{index:03}", "verifier", _build_verify_task(changes, context, directory))
        for index, changes in enumerate(merchant_changes, start=1)
    ]
    _write_jobs(directory, VERIFY_STAGE, [[step] for step in steps])


def holds_tasks(directory: Path, stage: str) -> bool:
    return any((directory / stage / "tasks").glob("*.json"))


def read_category_answers(directory: Path, stage: str) -> list[AgentAnswer]:
    return [
        AgentAnswer(
            transaction_id=str(raw_answer["id"]),
            category_key=raw_answer.get("category"),
            confidence=str(raw_answer.get("confidence", "")),
            reason=str(raw_answer.get("reason", "")),
            searchable=raw_answer.get("searchable") is not False,
        )
        for path, raw_answer in _read_answers(directory, stage)
    ]


def find_faulty_category_tasks(directory: Path, stage: str) -> tuple[FaultyTask, ...]:
    faulty_tasks: list[FaultyTask] = []
    for task_path in sorted((directory / stage / "tasks").glob("*.json")):
        answer_path = directory / stage / "answers" / task_path.name
        problems = _check_category_answer(_read_json(task_path), answer_path)
        if problems:
            faulty_tasks.append(FaultyTask(task_path, answer_path, problems))
    return tuple(faulty_tasks)


def remove_rerun_jobs(directory: Path, stage: str) -> None:
    (directory / stage / _RERUN_JOBS_FILE_NAME).unlink(missing_ok=True)


def write_rerun_jobs(directory: Path, stage: str, faulty_tasks: tuple[FaultyTask, ...]) -> Path:
    steps: list[JobStep] = []
    for faulty_task in faulty_tasks:
        raw_task = _read_json(faulty_task.task_path)
        rerun_count = int(raw_task.get("rerunCount", 0))
        if rerun_count >= _RERUN_LIMIT:
            raise AnswerError(f"{stage} {faulty_task.task_path.name} failed {rerun_count + 1} times: " + "; ".join(faulty_task.problems))

        raw_task |= {"rerunCount": rerun_count + 1, "problemsOfTheLastAnswer": list(faulty_task.problems)}
        faulty_task.task_path.write_text(json.dumps(raw_task, ensure_ascii=False, indent=1), encoding="utf-8")
        faulty_task.answer_path.unlink(missing_ok=True)
        steps.append(JobStep("categorizer", faulty_task.task_path.resolve(), faulty_task.answer_path.resolve(), f"{stage} {faulty_task.task_path.stem} again"))

    _write_jobs(directory, stage, [[step] for step in steps], _RERUN_JOBS_FILE_NAME)
    return directory / stage / _RERUN_JOBS_FILE_NAME


def read_research_findings(directory: Path, researched_on: date) -> tuple[KnownPlace, ...]:
    answer_paths = sorted((directory / RESEARCH_STAGE / "answers").glob("*.json"))
    raw_findings = [_read_json(path) for path in answer_paths]
    return tuple(
        KnownPlace(
            merchant_key=str(raw_finding["merchant"]),
            place=str(raw_finding.get("place") or ""),
            source=raw_finding.get("source"),
            trust=str(raw_finding.get("trust") or "none"),
            researched_on=str(raw_finding.get("researchedOn") or researched_on.isoformat()),
        )
        for raw_finding in raw_findings
        if isinstance(raw_finding, dict) and raw_finding.get("merchant")
    )


def read_verifier_rulings(directory: Path) -> dict[str, VerifierRuling]:
    rulings_by_transaction_id_map: dict[str, VerifierRuling] = {}
    for path, raw_answer in _read_answers(directory, VERIFY_STAGE):
        try:
            verdict = Verdict(raw_answer.get("decision"))
        except ValueError as error:
            raise AnswerError(f"{path.name}: decision {raw_answer.get('decision')!r} is neither keep nor reject") from error
        rulings_by_transaction_id_map[str(raw_answer["id"])] = VerifierRuling(verdict, str(raw_answer.get("reason", "")))
    return rulings_by_transaction_id_map


def _build_categorize_task(merchant_groups: tuple[MerchantGroup, ...], context: TaskContext) -> dict[str, Any]:
    return {
        "mode": context.mode,
        "location": vars(context.settings.location),
        "categories": context.category_full_names_by_key_map,
        "policy": str(context.policy_path),
        "confirmedExamples": [f"{example.payee} → {example.category_name}: {example.reason}" for example in context.examples],
        "merchants": [_write_merchant_group(group) for group in merchant_groups],
    }


def _build_research_task(group: MerchantGroup, context: TaskContext) -> dict[str, Any]:
    return {
        "merchant": group.merchant_key,
        "payees": sorted({transaction.payee for transaction in group.transactions}),
        "location": vars(context.settings.location),
        "transactions": [_write_transaction(transaction) for transaction in group.transactions[:5]],
    }


def _build_verify_task(merchant_changes: MerchantChanges, context: TaskContext, directory: Path) -> dict[str, Any]:
    group = merchant_changes.merchant_group
    research_tasks = sorted((directory / RESEARCH_STAGE / "tasks").glob("*.json"))
    research_task_path = next((path for path in research_tasks if _read_json(path).get("merchant") == group.merchant_key), None)
    research_path = directory / RESEARCH_STAGE / "answers" / research_task_path.name if research_task_path else None
    if research_path is not None and not research_path.exists():
        research_path = None
    return {
        "categories": context.category_full_names_by_key_map,
        "policy": str(context.policy_path),
        "merchant": _write_merchant_group(group),
        "research": str(research_path.resolve()) if research_path else None,
        "proposedChanges": [
            {
                "id": change.transaction.id,
                "currentCategory": change.transaction.category_name,
                "proposedCategory": change.proposal.category.full_name,
                "confidence": change.proposal.confidence.value,
                "reason": change.proposal.reason,
            }
            for change in merchant_changes.changes
        ],
    }


def _write_merchant_group(group: MerchantGroup) -> dict[str, Any]:
    return {
        "merchant": group.merchant_key,
        "habit": _write_habit(group.habit),
        "otherCategories": group.other_category_counts_by_name_map,
        "transactions": [_write_transaction(transaction) for transaction in group.transactions],
    }


def _write_habit(habit: MerchantHabit | None) -> dict[str, Any] | None:
    if habit is None:
        return None

    return {
        "paymentsInSnapshot": habit.payment_count,
        "months": habit.month_count,
        "usualAmount": habit.usual_amount,
        "monthlySameAmount": habit.is_monthly_same_amount,
    }


def _write_transaction(transaction: Transaction) -> dict[str, Any]:
    return {
        "id": transaction.id,
        "date": transaction.date.isoformat(),
        "weekday": transaction.date.strftime("%a"),
        "account": transaction.account_name,
        "amount": transaction.signed_amount(),
        "payee": transaction.payee,
        "comment": transaction.comment,
        "currentCategory": transaction.category_name,
    }


def _write_task(directory: Path, stage: str, name: str, agent: str, raw_task: dict[str, Any]) -> JobStep:
    task_path = directory / stage / "tasks" / f"{name}.json"
    answer_path = directory / stage / "answers" / f"{name}.json"
    task_path.parent.mkdir(parents=True, exist_ok=True)
    answer_path.parent.mkdir(parents=True, exist_ok=True)
    answer_path.unlink(missing_ok=True)
    task_path.write_text(json.dumps(raw_task, ensure_ascii=False, indent=1), encoding="utf-8")
    return JobStep(agent, task_path.resolve(), answer_path.resolve(), f"{stage} {name}")


def _write_known_place(known_place: KnownPlace, answer_path: Path) -> None:
    raw_answer = {
        "merchant": known_place.merchant_key,
        "place": known_place.place,
        "source": known_place.source,
        "trust": known_place.trust,
        "researchedOn": known_place.researched_on,
    }
    answer_path.write_text(json.dumps(raw_answer, ensure_ascii=False, indent=1), encoding="utf-8")


def _clear_stages(directory: Path, *stages: str) -> None:
    for stage in stages:
        for stale_path in (directory / stage).glob("*/*.json"):
            stale_path.unlink()


def _check_category_answer(raw_task: dict[str, Any], answer_path: Path) -> tuple[str, ...]:
    if not answer_path.exists():
        return ("no answer file was written",)
    try:
        raw_answers = _read_json(answer_path)
    except AnswerError:
        return ("the answer file is not valid JSON",)
    if not isinstance(raw_answers, list):
        return ("the answer file must hold a JSON list",)

    expected_ids = {transaction["id"] for merchant in raw_task["merchants"] for transaction in merchant["transactions"]}
    answered_ids = [raw_answer.get("id") for raw_answer in raw_answers if isinstance(raw_answer, dict)]
    problems: list[str] = []
    if len(answered_ids) != len(raw_answers):
        problems.append("every answer must be an object with an id")
    if expected_ids - set(answered_ids):
        problems.append(f"no answer for the transactions {sorted(expected_ids - set(answered_ids))}")
    if set(answered_ids) - expected_ids:
        problems.append(f"answers for ids that the task does not hold: {sorted(set(answered_ids) - expected_ids)}")
    if len(answered_ids) != len(set(answered_ids)):
        problems.append("a transaction is answered more than once")

    for raw_answer in raw_answers:
        if not isinstance(raw_answer, dict):
            continue
        if raw_answer.get("category") is not None and raw_answer.get("category") not in raw_task["categories"]:
            problems.append(f"{raw_answer.get('id')}: category {raw_answer.get('category')!r} is not a key of categories")
        if raw_answer.get("confidence") not in {confidence.value for confidence in Confidence}:
            problems.append(f"{raw_answer.get('id')}: confidence {raw_answer.get('confidence')!r} is none of high, medium, low")
    return tuple(problems)


def _write_jobs(directory: Path, stage: str, jobs: list[list[JobStep]], file_name: str = _JOBS_FILE_NAME) -> None:
    raw_jobs = [
        [{"agent": step.agent, "task": str(step.task_path), "answer": str(step.answer_path), "label": step.label} for step in job]
        for job in jobs
    ]
    jobs_text = json.dumps({"stage": stage, "jobs": raw_jobs}, ensure_ascii=False, indent=1)
    (directory / stage).mkdir(parents=True, exist_ok=True)
    (directory / stage / file_name).write_text(
        f"export const meta = {{ name: 'zenmoney-cleaner-{stage}-jobs', description: 'Jobs of the {stage} stage' }}\n"
        f"return {jobs_text}\n",
        encoding="utf-8",
    )


def _read_answers(directory: Path, stage: str) -> list[tuple[Path, dict[str, Any]]]:
    task_paths = sorted((directory / stage / "tasks").glob("*.json"))
    answer_folder = directory / stage / "answers"
    missing_names = [path.name for path in task_paths if not (answer_folder / path.name).exists()]
    if missing_names:
        raise AnswerError(f"{stage}: no answers yet for {missing_names}; run the {stage} jobs again")

    answers: list[tuple[Path, dict[str, Any]]] = []
    for path in task_paths:
        raw_answers = _read_json(answer_folder / path.name)
        if not isinstance(raw_answers, list):
            raise AnswerError(f"{stage} {path.name}: the answer must be a list")
        for raw_answer in raw_answers:
            if not isinstance(raw_answer, dict) or "id" not in raw_answer:
                raise AnswerError(f"{stage} {path.name}: every answer needs an id, found {raw_answer!r}")
            answers.append((path, raw_answer))
    return answers


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise AnswerError(f"{path} is not valid JSON: {error}") from error
