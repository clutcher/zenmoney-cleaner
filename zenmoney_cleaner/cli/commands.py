import argparse
import json
import sys
from dataclasses import dataclass
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

from zenmoney_cleaner.applying.approval import ProposalFormatError, approve_proposal
from zenmoney_cleaner.categorizing.agent_answers import AnswerError, judge_by_answers, list_unsearchable_transaction_ids
from zenmoney_cleaner.categorizing.category_catalog import CategoryCatalog, UnknownCategoryError
from zenmoney_cleaner.categorizing.categorizing_scope import CategorizingMode, CategorizingScope
from zenmoney_cleaner.categorizing.category_proposal import (
    CategorySelection,
    propose_categories,
    select_changes_to_verify,
    select_for_categorizing,
    select_merchants_to_research,
)
from zenmoney_cleaner.categorizing.judgement import Judgement
from zenmoney_cleaner.categorizing.category_tasks import MerchantGroup, split_into_tasks
from zenmoney_cleaner.categorizing.rule_categorizer import RuleCategorizer, TransferTargetError
from zenmoney_cleaner.corrections.correction_chains import MissingAdjustmentCategoryError, find_correction_chains
from zenmoney_cleaner.files.corrections_file import write_corrections_proposal
from zenmoney_cleaner.files.history_file import read_history, write_history
from zenmoney_cleaner.files.first_settings_file import HomeAlreadySetUpError, write_first_settings
from zenmoney_cleaner.files.proposal_file import write_category_proposal
from zenmoney_cleaner.categorizing.known_places import KnownPlaces
from zenmoney_cleaner.files.places_file import read_known_places, record_places
from zenmoney_cleaner.files.settings_file import SettingsError, read_settings
from zenmoney_cleaner.files.scope_file import MissingScopeError, read_scope, write_scope
from zenmoney_cleaner.files.snapshot_file import read_snapshot, write_snapshot
from zenmoney_cleaner.files.task_file import (
    CATEGORIZE_STAGE,
    REJUDGE_STAGE,
    RESEARCH_STAGE,
    VERIFY_STAGE,
    TaskContext,
    find_faulty_category_tasks,
    holds_tasks,
    read_category_answers,
    remove_rerun_jobs,
    read_research_findings,
    read_verifier_rulings,
    write_categorize_jobs,
    write_research_jobs,
    write_rerun_jobs,
    write_verify_jobs,
)
from zenmoney_cleaner.files.verified_file import read_verified_transactions, record_confirmations
from zenmoney_cleaner.home.home_folder import HOME_VARIABLE, HomeFinder, HomePlace, MissingHomeError
from zenmoney_cleaner.payee.merchant_key import MerchantKeyMaker
from zenmoney_cleaner.settings.category_keys import make_category_names_by_key_map
from zenmoney_cleaner.settings.settings import Confidence, Location, Settings
from zenmoney_cleaner.snapshot.snapshot import Snapshot
from zenmoney_cleaner.snapshot.transaction import TransactionKind
from zenmoney_cleaner.snapshot.snapshot_merger import IncompletePagesError, UnknownAccountError, merge_snapshot, read_categories

_RERUN_EXIT_CODE = 2
_PLACES_FILE_NAME = "places.yml"
_HISTORY_FILE_NAME = "history.json"
_EXAMPLE_FOLDER = Path(__file__).resolve().parents[2] / "config.example"


class MissingFetchRangeError(Exception):
    pass


class MissingLastCheckError(Exception):
    pass


_USER_ERRORS = (
    MissingFetchRangeError,
    MissingLastCheckError,
    SettingsError,
    UnknownCategoryError,
    TransferTargetError,
    IncompletePagesError,
    UnknownAccountError,
    AnswerError,
    MissingScopeError,
    MissingAdjustmentCategoryError,
    ProposalFormatError,
    MissingHomeError,
    HomeAlreadySetUpError,
)


class RerunNeededError(Exception):
    pass



def main(arguments: list[str] | None = None) -> int:
    parsed_arguments = _build_parser().parse_args(arguments)
    try:
        if parsed_arguments.needs_home:
            parsed_arguments.home_path = _require_home(parsed_arguments.home)
            print(f"home: {parsed_arguments.home_path}")
        parsed_arguments.command(parsed_arguments)
    except RerunNeededError as error:
        print(f"rerun: {error}")
        return _RERUN_EXIT_CODE
    except _USER_ERRORS as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


def home(arguments: argparse.Namespace) -> None:
    finder = HomeFinder.for_this_process()
    home_folder = finder.find_home(None)
    if home_folder is not None:
        print(f"home: {home_folder.path} (found through {home_folder.source.value})")
        return

    print("home: none found; the setup skill creates 1 of these:")
    print(f"{HomePlace.PROJECT.value}: {finder.locate(HomePlace.PROJECT)} (this folder only)")
    print(f"{HomePlace.USER_ACCOUNT.value}: {finder.locate(HomePlace.USER_ACCOUNT)} (works from any folder)")


def init(arguments: argparse.Namespace) -> None:
    home_path = HomeFinder.for_this_process().locate(HomePlace(arguments.place))
    categories_response = json.loads(Path(arguments.categories).read_text(encoding="utf-8"))
    categories = read_categories(categories_response["data"])
    category_names_by_key_map = make_category_names_by_key_map(categories, categories_response.get("balanceAdjustmentCategoryId"))

    write_first_settings(home_path, Location(arguments.country, arguments.country_code, arguments.city), category_names_by_key_map, _EXAMPLE_FOLDER)
    print(f"home: {home_path} created, with {len(category_names_by_key_map)} categories in config.yml and the example policy.md")


def merge(arguments: argparse.Namespace) -> None:
    pages_by_query = [
        [json.loads(path.read_text(encoding="utf-8")) for path in sorted(Path(folder).glob("*.json"))] for folder in arguments.pages
    ]
    categories_response = json.loads(Path(arguments.categories).read_text(encoding="utf-8"))
    accounts_response = json.loads(Path(arguments.accounts).read_text(encoding="utf-8"))

    snapshot = merge_snapshot(pages_by_query, categories_response, accounts_response)
    if arguments.history:
        if not (arguments.fetched_from and arguments.fetched_to):
            raise MissingFetchRangeError("--history needs --fetched-from and --fetched-to, the range of the main query")
        snapshot = _keep_history(snapshot, Path(arguments.history), date.fromisoformat(arguments.fetched_from), date.fromisoformat(arguments.fetched_to))

    write_snapshot(snapshot, Path(arguments.out))
    page_count = sum(len(query_pages) for query_pages in pages_by_query)
    print(f"snapshot: {len(snapshot.transactions)} transactions from {page_count} pages → {arguments.out}")


def _keep_history(snapshot: Snapshot, history_path: Path, fetched_from: date, fetched_to: date) -> Snapshot:
    history = read_history(history_path).replace_range(snapshot.transactions, fetched_from, fetched_to)
    write_history(history, history_path)
    return snapshot.with_history_transactions(history.list_transactions(snapshot))


def fetch_range(arguments: argparse.Namespace) -> None:
    settings = read_settings(arguments.home_path / "config.yml")
    history = read_history(arguments.home_path / _HISTORY_FILE_NAME)

    days_to_fetch = history.plan_fetch(date.today(), settings.history.overlap_days)

    print(f"from: {days_to_fetch.from_date.isoformat()}")
    print(f"to: {days_to_fetch.to_date.isoformat()}")
    if days_to_fetch.is_first_run:
        print("first run: history.json holds no transactions yet, so the fetch takes 3 months")


def prepare(arguments: argparse.Namespace) -> None:
    write_scope(_read_scope_arguments(arguments, arguments.home_path), Path(arguments.out))
    run = _open_run(arguments)

    tasks = split_into_tasks(run.selection.merchant_groups)

    write_categorize_jobs(tasks, run.context, run.out)
    print(
        f"prepared ({run.scope.mode.value}): {len(run.selection.rule_judgements)} transactions decided by rules, "
        f"{len(run.selection.list_agent_transaction_ids())} transactions of {len(run.selection.merchant_groups)} merchants "
        f"in {len(tasks)} categorize jobs → {run.out / CATEGORIZE_STAGE / 'jobs.workflow.js'}"
    )


def route(arguments: argparse.Namespace) -> None:
    run = _open_run(arguments)
    first_judgements_by_transaction_id_map = _judge_first(run)

    merchant_groups = _select_researched_groups(run, first_judgements_by_transaction_id_map)
    known_places = KnownPlaces.none() if arguments.research_again else read_known_places(run.home / _PLACES_FILE_NAME)

    write_research_jobs(merchant_groups, known_places, run.context, run.out)
    known_count = sum(1 for group in merchant_groups if known_places.knows(group.merchant_key))
    print(
        f"routed: {len(merchant_groups) - known_count} merchants to research, {known_count} judged again with the places "
        f"researched before → {run.out / RESEARCH_STAGE / 'jobs.workflow.js'}"
    )


def verify(arguments: argparse.Namespace) -> None:
    run = _open_run(arguments)
    judgements_by_transaction_id_map = _judge_finally(run)
    if holds_tasks(run.out, RESEARCH_STAGE):
        record_places(run.home / _PLACES_FILE_NAME, read_research_findings(run.out, date.today()))

    merchant_changes = select_changes_to_verify(run.selection, judgements_by_transaction_id_map)

    write_verify_jobs(merchant_changes, run.context, run.out)
    change_count = sum(len(changes.changes) for changes in merchant_changes)
    print(f"to verify: {change_count} changes of your categories at {len(merchant_changes)} merchants → {run.out / VERIFY_STAGE / 'jobs.workflow.js'}")


def propose(arguments: argparse.Namespace) -> None:
    run = _open_run(arguments)
    judgements_by_transaction_id_map = _judge_finally(run)
    rulings_by_transaction_id_map = read_verifier_rulings(run.out) if holds_tasks(run.out, VERIFY_STAGE) else {}

    proposal = propose_categories(run.selection, judgements_by_transaction_id_map, rulings_by_transaction_id_map, run.scope)

    write_category_proposal(proposal, run.catalog, run.out)
    print(
        f"proposal ({run.scope.mode.value}): {len(proposal.changes)} changes, {len(proposal.agreements)} confirmed, "
        f"{len(proposal.unknown_merchants)} merchants undecided → {run.out / 'proposal.md'}"
    )


@dataclass(frozen=True)
class _Run:
    home: Path
    out: Path
    scope: CategorizingScope
    selection: CategorySelection
    catalog: CategoryCatalog
    context: TaskContext


def _open_run(arguments: argparse.Namespace) -> _Run:
    home = arguments.home_path
    settings = read_settings(home / "config.yml")
    policy_path = home / "policy.md"
    if not policy_path.exists():
        raise SettingsError(f"{policy_path} is missing; copy policy.md of config.example and write your rules into it")

    snapshot = _read_snapshot(Path(arguments.snapshot), settings)
    catalog = CategoryCatalog.resolve(settings.category_names_by_key_map, snapshot)
    verified_transactions = read_verified_transactions(home / "verified.yml")
    scope = read_scope(Path(arguments.out))
    selection = select_for_categorizing(
        snapshot=snapshot,
        rule_categorizer=RuleCategorizer(settings, catalog, snapshot),
        key_maker=MerchantKeyMaker(settings.payee_strip_patterns),
        verified_transactions=verified_transactions,
        scope=scope,
    )
    context = TaskContext(settings, catalog.describe_categories(), scope.mode.value, policy_path.resolve(), verified_transactions.list_examples())
    return _Run(home, Path(arguments.out), scope, selection, catalog, context)


def _read_snapshot(path: Path, settings: Settings) -> Snapshot:
    snapshot = read_snapshot(path)
    adjustment_category_name = settings.corrections.adjustment_category_name
    if adjustment_category_name is None:
        return snapshot

    adjustment_category = snapshot.find_category(adjustment_category_name)
    if adjustment_category is None:
        raise SettingsError(f"config.yml, corrections.adjustment_category: Zenmoney has no category {adjustment_category_name!r}")
    return snapshot.with_balance_adjustment_category(adjustment_category.id)


def _read_scope_arguments(arguments: argparse.Namespace, home: Path) -> CategorizingScope:
    mode = CategorizingMode(arguments.mode)
    from_date = _read_period_start(arguments.from_period) if arguments.from_period else None
    if mode == CategorizingMode.SINCE_LAST_CHECK:
        from_date = _read_last_check(home)

    return CategorizingScope(
        mode=mode,
        from_date=from_date,
        to_date=_read_period_end(arguments.to_period) if arguments.to_period else None,
        account_names=frozenset(arguments.account),
        kind=TransactionKind(arguments.type) if arguments.type else None,
    )


def _read_last_check(home: Path) -> date:
    last_check = read_history(home / _HISTORY_FILE_NAME).last_check
    if last_check is None:
        raise MissingLastCheckError("history.json records no check yet; approve a run of another mode first")

    return last_check


def _read_period_start(period: str) -> date:
    if len(period) == len("YYYY-MM"):
        return date.fromisoformat(f"{period}-01")
    return date.fromisoformat(period)


def _read_period_end(period: str) -> date:
    if len(period) != len("YYYY-MM"):
        return date.fromisoformat(period)

    first_day = date.fromisoformat(f"{period}-01")
    next_month_first_day = date(first_day.year + first_day.month // 12, first_day.month % 12 + 1, 1)
    return next_month_first_day - timedelta(days=1)


def _judge_first(run: _Run) -> dict[str, Judgement]:
    _require_sound_answers(run, CATEGORIZE_STAGE)
    answers = read_category_answers(run.out, CATEGORIZE_STAGE)
    return judge_by_answers(answers, run.selection.list_agent_transaction_ids(), run.catalog)


def _judge_finally(run: _Run) -> dict[str, Judgement]:
    first_judgements_by_transaction_id_map = _judge_first(run)
    if not holds_tasks(run.out, REJUDGE_STAGE):
        return first_judgements_by_transaction_id_map

    _require_sound_answers(run, REJUDGE_STAGE)
    researched_groups = _select_researched_groups(run, first_judgements_by_transaction_id_map)
    researched_ids = {transaction_id for group in researched_groups for transaction_id in group.list_transaction_ids()}
    second_judgements_by_transaction_id_map = judge_by_answers(read_category_answers(run.out, REJUDGE_STAGE), researched_ids, run.catalog)
    return first_judgements_by_transaction_id_map | second_judgements_by_transaction_id_map


def _select_researched_groups(run: _Run, first_judgements_by_transaction_id_map: dict[str, Judgement]) -> tuple[MerchantGroup, ...]:
    unsearchable_ids = list_unsearchable_transaction_ids(read_category_answers(run.out, CATEGORIZE_STAGE))
    return select_merchants_to_research(run.selection, first_judgements_by_transaction_id_map, unsearchable_ids)


def _require_sound_answers(run: _Run, stage: str) -> None:
    faulty_tasks = find_faulty_category_tasks(run.out, stage)
    if not faulty_tasks:
        remove_rerun_jobs(run.out, stage)
        return

    rerun_jobs_path = write_rerun_jobs(run.out, stage, faulty_tasks)
    problems_text = "; ".join(f"{task.task_path.stem}: {', '.join(task.problems)}" for task in faulty_tasks)
    raise RerunNeededError(
        f"{len(faulty_tasks)} {stage} jobs answered wrongly ({problems_text}); run the Workflow for {rerun_jobs_path}, then this command again"
    )


def approve(arguments: argparse.Namespace) -> None:
    home = arguments.home_path
    raw_proposal = json.loads(Path(arguments.proposal).read_text(encoding="utf-8"))

    chosen_category_keys_by_merchant_key_map = dict(choice.rsplit("=", 1) for choice in arguments.set)
    skipped_merchant_keys = set(arguments.skip)
    kept_undecided_merchant_keys: set[str | None] = set()
    if arguments.keep_other_undecided:
        kept_undecided_merchant_keys = {
            item["merchantKey"] for item in raw_proposal.get("undecided", [])
        } - skipped_merchant_keys - set(chosen_category_keys_by_merchant_key_map)
    approval = approve_proposal(
        raw_proposal,
        Confidence(arguments.min_confidence),
        skipped_merchant_keys,
        set(arguments.keep),
        chosen_category_keys_by_merchant_key_map,
        kept_undecided_merchant_keys,
    )

    raw_batches = {
        "upsertBatches": [list(batch) for batch in approval.upsert_batches],
        "deleteBatches": [list(batch) for batch in approval.delete_batches],
    }
    Path(arguments.out).write_text(json.dumps(raw_batches, ensure_ascii=False, indent=1), encoding="utf-8")
    record_confirmations(home / "verified.yml", approval.confirmations, date.today())
    if approval.checked_until is not None:
        history_path = home / _HISTORY_FILE_NAME
        write_history(read_history(history_path).record_check(approval.checked_until), history_path)
    upsert_count = sum(len(batch) for batch in approval.upsert_batches)
    delete_count = sum(len(batch) for batch in approval.delete_batches)
    print(
        f"approved: {upsert_count} updates, {delete_count} deletions → {arguments.out}; "
        f"{len(approval.confirmations)} transactions recorded as verified"
    )


def corrections(arguments: argparse.Namespace) -> None:
    settings = read_settings(arguments.home_path / "config.yml")
    snapshot = _read_snapshot(Path(arguments.snapshot), settings)

    report = find_correction_chains(snapshot, settings.corrections)

    write_corrections_proposal(report, Path(arguments.out))
    deletion_count = sum(len(chain.corrections) for chain in report.closed_chains)
    print(
        f"corrections: {len(report.closed_chains)} closed chains with {deletion_count} corrections to delete, "
        f"{len(report.open_chains)} open chains → {Path(arguments.out) / 'proposal.md'}"
    )


def _read_choice(text: str) -> str:
    if "=" not in text:
        raise argparse.ArgumentTypeError(f"{text!r} is not MERCHANT KEY=category key")
    return text


def _require_home(option: str | None) -> Path:
    finder = HomeFinder.for_this_process()
    home_folder = finder.find_home(option)
    if home_folder is None:
        raise MissingHomeError(
            f"no home folder with config.yml found; the setup skill creates it in {finder.locate(HomePlace.PROJECT)} "
            f"or {finder.locate(HomePlace.USER_ACCOUNT)}"
        )

    return home_folder.path


def _add_home_argument(step_parser: argparse.ArgumentParser, help_text: str) -> None:
    step_parser.add_argument("--home", help=f"folder of {help_text}; else ${HOME_VARIABLE}, else ./zenmoney-cleaner, else the folder of your user account")
    step_parser.set_defaults(needs_home=True)


def _add_run_arguments(step_parser: argparse.ArgumentParser, command: Callable[[argparse.Namespace], None]) -> None:
    step_parser.add_argument("--snapshot", required=True)
    step_parser.add_argument("--out", required=True, help="run folder of the scope, the stages and the proposal files")
    _add_home_argument(step_parser, "config.yml, policy.md, verified.yml, places.yml")
    step_parser.set_defaults(command=command)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="zenmoney_cleaner")
    subparsers = parser.add_subparsers(required=True)

    home_parser = subparsers.add_parser("home", help="print the home folder found, or the 2 places the setup can create it")
    home_parser.set_defaults(command=home, needs_home=False)

    init_parser = subparsers.add_parser("init", help="create the home folder with config.yml from the Zenmoney categories and the example policy.md")
    init_parser.add_argument("--place", required=True, choices=[place.value for place in HomePlace], help="project: this folder only; user-account: works from any folder")
    init_parser.add_argument("--categories", required=True, help="saved list_categories response")
    init_parser.add_argument("--country", required=True)
    init_parser.add_argument("--country-code", required=True, help="2-letter code of the country")
    init_parser.add_argument("--city", help="home city; optional")
    init_parser.set_defaults(command=init, needs_home=False)

    merge_parser = subparsers.add_parser("merge", help="join fetched pages into 1 snapshot")
    merge_parser.add_argument(
        "--pages", required=True, action="append", help="folder of the list_transactions pages of 1 query; repeat for each query"
    )
    merge_parser.add_argument("--categories", required=True, help="saved list_categories response")
    merge_parser.add_argument("--accounts", required=True, help="saved list_accounts response")
    merge_parser.add_argument("--out", required=True, help="snapshot file to write")
    merge_parser.add_argument("--history", help="history.json of the home folder: the fetched range replaces that range in it, and the rest joins the snapshot as history")
    merge_parser.add_argument("--fetched-from", help="first day of the main query as YYYY-MM-DD; needed with --history")
    merge_parser.add_argument("--fetched-to", help="last day of the main query as YYYY-MM-DD; needed with --history")
    merge_parser.set_defaults(command=merge, needs_home=False)

    fetch_range_parser = subparsers.add_parser("fetch-range", help="print the days to fetch: since the newest day of history.json minus history.overlap_days, or 3 months on the first run")
    _add_home_argument(fetch_range_parser, "config.yml and history.json")
    fetch_range_parser.set_defaults(command=fetch_range)

    prepare_parser = subparsers.add_parser("prepare", help="save the scope, decide by rules and write the categorize jobs for the rest")
    prepare_parser.add_argument("--mode", choices=[mode.value for mode in CategorizingMode], required=True,
                                help="without-category: only transactions with no category; new-in-zenmoney: only those Zenmoney shows as New; recheck-all: every transaction of the scope; since-last-check: every transaction from the day of the last approved check, that day included")
    prepare_parser.add_argument("--from", dest="from_period", help="first day as YYYY-MM-DD, or a month as YYYY-MM for its first day")
    prepare_parser.add_argument("--to", dest="to_period", help="last day as YYYY-MM-DD, or a month as YYYY-MM for its last day")
    prepare_parser.add_argument("--account", action="append", default=[], help="account name; repeatable")
    prepare_parser.add_argument("--type", choices=[TransactionKind.EXPENSE.value, TransactionKind.INCOME.value])
    _add_run_arguments(prepare_parser, prepare)

    route_parser = subparsers.add_parser("route", help="check the categorize answers and write the research jobs for the unsure merchants")
    route_parser.add_argument(
        "--research-again", action="store_true", help="search the web again also for the merchants that places.yml already holds"
    )
    _add_run_arguments(route_parser, route)

    for name, command, help_text in (
        ("verify", verify, "record the researched places and write the verify jobs for the changes of categories the user set"),
        ("propose", propose, "check all answers and write the proposal"),
    ):
        _add_run_arguments(subparsers.add_parser(name, help=help_text), command)

    corrections_parser = subparsers.add_parser("corrections", help="find closed and open chains of balance corrections")
    corrections_parser.add_argument("--snapshot", required=True)
    corrections_parser.add_argument("--out", required=True, help="folder for proposal.json and proposal.md")
    _add_home_argument(corrections_parser, "config.yml")
    corrections_parser.set_defaults(command=corrections)

    approve_parser = subparsers.add_parser("approve", help="turn the approved part of a proposal into connector batches and record it as verified")
    approve_parser.add_argument("--proposal", required=True)
    approve_parser.add_argument("--min-confidence", choices=[confidence.value for confidence in Confidence], default="high")
    approve_parser.add_argument("--skip", action="append", default=[], help="merchant key left undecided; repeatable")
    approve_parser.add_argument("--keep", action="append", default=[], help="merchant key whose current category the user confirmed; repeatable")
    approve_parser.add_argument(
        "--keep-other-undecided", action="store_true", help="confirm the current category of every undecided merchant that --skip and --set do not name"
    )
    approve_parser.add_argument(
        "--set", action="append", default=[], type=_read_choice, help="MERCHANT KEY=category key the user chose for that merchant; repeatable"
    )
    approve_parser.add_argument("--out", required=True, help="batches file to write")
    _add_home_argument(approve_parser, "verified.yml")
    approve_parser.set_defaults(command=approve)

    return parser
