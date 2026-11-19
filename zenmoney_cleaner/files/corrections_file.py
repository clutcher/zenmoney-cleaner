import json
from pathlib import Path
from typing import Any

from zenmoney_cleaner.corrections.correction_chains import ClosedChain, CorrectionReport, OpenChain
from zenmoney_cleaner.files.proposal_file import write_transaction_line
from zenmoney_cleaner.snapshot.transaction import Transaction

_CLOSED_CHAIN_REASON = "the corrections of this chain add up to 0, so deleting them leaves the balance as it is"


def write_corrections_proposal(report: CorrectionReport, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    raw_changes = [_write_deletion(chain, correction) for chain in report.closed_chains for correction in chain.corrections]
    raw_open_chains = [_write_open_chain(chain) for chain in report.open_chains]

    (directory / "proposal.json").write_text(
        json.dumps({"mode": "corrections", "changes": raw_changes, "openChains": raw_open_chains}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    (directory / "proposal.md").write_text(_render_markdown(report), encoding="utf-8")


def _name_chain(chain: ClosedChain) -> str:
    return f"{chain.account_name} {chain.corrections[0].date.isoformat()}"


def _write_deletion(chain: ClosedChain, correction: Transaction) -> dict[str, Any]:
    return {
        "merchantKey": _name_chain(chain),
        "transaction": write_transaction_line(correction),
        "action": "delete",
        "confidence": "high",
        "reason": _CLOSED_CHAIN_REASON,
        "source": "corrections",
        "deleteId": correction.id,
    }


def _write_open_chain(chain: OpenChain) -> dict[str, Any]:
    return {
        "account": chain.account_name,
        "residual": chain.residual,
        "pending": chain.is_pending,
        "corrections": [write_transaction_line(correction) for correction in chain.corrections],
        "matches": [
            {
                "correctionId": match.correction.id,
                "transactionSets": [[write_transaction_line(transaction) for transaction in transaction_set] for transaction_set in match.transaction_sets],
            }
            for match in chain.matches
        ],
        "suspects": [write_transaction_line(transaction) for transaction in chain.suspects],
    }


def _render_markdown(report: CorrectionReport) -> str:
    deletion_count = sum(len(chain.corrections) for chain in report.closed_chains)
    lines = [
        "# Balance corrections",
        "",
        f"{len(report.closed_chains)} closed chains with {deletion_count} corrections to delete, {len(report.open_chains)} open chains.",
        "",
        "## Closed chains",
        "",
        "Each chain adds up to 0, so deleting it leaves the balance as it is.",
        "",
        "| Chain | Date | Amount |",
        "|---|---|---|",
    ]
    for chain in report.closed_chains:
        lines += [f"| {_name_chain(chain)} | {correction.date.isoformat()} | {correction.signed_amount()} |" for correction in chain.corrections]
    lines.append("")

    lines += ["## Open chains", ""]
    for chain in report.open_chains:
        state_text = "probably still pending at the bank" if chain.is_pending else "open for a while: a real difference"
        lines += [f"### {chain.account_name}: {chain.residual} ({state_text})", ""]
        lines += ["| Date | Correction | Real transactions that add up to it |", "|---|---|---|"]
        for match in chain.matches:
            sets_text = "; ".join(" + ".join(_describe(transaction) for transaction in transaction_set) for transaction_set in match.transaction_sets)
            lines.append(f"| {match.correction.date.isoformat()} | {match.correction.signed_amount()} | {sets_text or 'none found'} |")
        lines.append("")
        if chain.suspects:
            lines += [f"Transactions of the residual's amount: {', '.join(_describe(transaction) for transaction in chain.suspects)}.", ""]
    return "\n".join(lines) + "\n"


def _describe(transaction: Transaction) -> str:
    label = transaction.payee or transaction.comment or transaction.category_name or "no payee"
    return f"{transaction.date.isoformat()} {transaction.signed_amount()} {label}".replace("|", "/")
