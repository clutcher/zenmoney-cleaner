import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tests.support.zenmoney_responses import CONFIG_TEXT, build_page, read_json, write_fetch, write_home
from zenmoney_cleaner.cli.commands import main


@dataclass(frozen=True)
class CategorizingRun:
    home: Path
    snapshot_path: Path
    out: Path
    mode: str

    def run(self, command: str, *scope_options: str) -> int:
        mode_options = ["--mode", self.mode, *scope_options] if command == "prepare" else []
        return main([command, "--snapshot", str(self.snapshot_path), "--out", str(self.out), "--home", str(self.home), *mode_options])

    def read_tasks(self, stage: str) -> list[dict[str, Any]]:
        return [read_json(path) for path in sorted((self.out / stage / "tasks").glob("*.json"))]

    def answer_every_task(self, stage: str, answer_by_transaction_id: dict[str, dict[str, Any]]) -> None:
        for task_path in sorted((self.out / stage / "tasks").glob("*.json")):
            transaction_ids = [transaction["id"] for merchant in read_json(task_path)["merchants"] for transaction in merchant["transactions"]]
            answers = [{"id": transaction_id} | answer_by_transaction_id[transaction_id] for transaction_id in transaction_ids]
            self.write_answer(stage, task_path.name, answers)

    def write_answer(self, stage: str, name: str, raw_answer: Any) -> None:
        (self.out / stage / "answers" / name).write_text(json.dumps(raw_answer), encoding="utf-8")

    def read_proposal(self) -> dict[str, Any]:
        return read_json(self.out / "proposal.json")

    def read_changes_by_id_map(self) -> dict[str, dict[str, Any]]:
        return {change["transaction"]["id"]: change for change in self.read_proposal()["changes"]}


def start_run(tmp_path: Path, transactions: list[dict[str, Any]], mode: str, config_text: str = CONFIG_TEXT, verified_text: str | None = None) -> CategorizingRun:
    fetch = write_fetch(tmp_path, [build_page(transactions)])
    home = write_home(tmp_path, config_text)
    if verified_text is not None:
        (home / "verified.yml").write_text(verified_text, encoding="utf-8")
    snapshot_path = tmp_path / "snapshot.json"
    main([
        "merge",
        "--pages", str(fetch / "pages"),
        "--categories", str(fetch / "categories.json"),
        "--accounts", str(fetch / "accounts.json"),
        "--out", str(snapshot_path),
    ])
    return CategorizingRun(home, snapshot_path, tmp_path / "run", mode)
