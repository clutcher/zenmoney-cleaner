---
name: corrections
description: Clean up the balance corrections that a Zenmoney bank sync stacks up, by deleting the chains of corrections that add up to 0 and showing, for each correction still open, the real transactions that explain it, then apply the deletions the user approves. Use when the user asks to clean up, review or fix balance corrections, auto-adjustments or the balance-adjustment category in Zenmoney, in any language.
---

# Clean up balance corrections

You run these steps in order and decide nothing the steps do not name. The code finds the chains; the user decides every deletion.

`<cli>` stands for `PYTHONPATH="${CLAUDE_PLUGIN_ROOT}" python3 -m zenmoney_cleaner`, `<out>` for the folder `<run>/corrections`. `<home>` is the folder that `<cli> home` prints; every command finds it the same way by itself and prints it. Where it finds none, run the setup skill of zenmoney-cleaner first.

Never rename, edit or delete the balance-adjustment category itself, and never move a transaction into or out of it: after a rename or a second category of the same name, `list_categories` reports its id `balanceAdjustmentCategoryId` as null. The code reads that id, or the category that `corrections.adjustment_category` of `config.yml` names.

## 1. Snapshot

Where `config.yml` holds no `corrections.adjustment_category`, call `list_categories`. Where its `balanceAdjustmentCategoryId` is null, list the likely categories: names that mean correction or adjustment in any language, such as Корректировка, and the category that `corrections` names in its error, whose transactions are mostly synced with no payee. Ask the user which one it is, and write its name as `corrections.adjustment_category` into `config.yml`.

Run the fetch-transactions skill with its correction history query, for the last 3 months, unless a snapshot of today holds `correction-pages/` and no change was made in Zenmoney since. The 3 months give the real purchases that an open correction is matched against.

## 2. Find the chains

Run `<cli> corrections --snapshot <run>/snapshot.json --out <out>`. Per account, it takes only the corrections a sync made: those in the balance-adjustment category with a sync source and no payee, so an entry the user typed into that category is never touched. It writes `proposal.md` and `proposal.json` into `<out>`:

- Closed chains: runs of consecutive corrections that add up to 0 within 0.01. Deleting such a chain leaves every balance as it was.
- Open chains: the corrections left per account, their sum as the residual, the real transactions of up to `corrections.match_window_days` days before each one whose amounts add up to it, and the transactions whose amount equals the residual. A chain whose last correction is less than a week older than the newest transaction is marked pending, because the bank has usually not settled those purchases yet.

## 3. Review with the user

Show the closed chains as a table per chain with the dates and amounts, then the open chains. For an open chain, say what the matches suggest in 1 line each: a purchase the bank charged at another amount, a purchase still pending, or nothing found. A match of several small purchases is a hint only, because many sets of small amounts add up to the same sum. An open chain is never deleted by this skill: a residual that stays open is a real difference, which the user fixes in Zenmoney, such as a missing or double transaction, and the next fetch shows whether it closed.

## 4. Approve and apply

Agree on the chains to leave, by their name as `proposal.md` shows it, such as `Card 2026-10-09`. Run `<cli> approve --proposal <out>/proposal.json --min-confidence high --skip <chain name> --out <out>/batches.json` only after the user approved.

Show the user the transactions of each list of `deleteBatches` once more, with their count and the sum per account, which is 0 for every closed chain, and get a yes for that deletion, because Zenmoney cannot restore a deleted transaction. Then send it to `delete_transactions`. Append each result to `<out>/applied.json`, so a stopped run resumes at the first batch with no result. Report what was deleted, and suggest a new fetch before the next run.
