---
name: categorize
description: Categorize Zenmoney transactions that have no category, check the transactions Zenmoney shows as New, or recheck the categories of a period, an account or a type, with strict rules, a categorizer agent, web research of unknown places and a verifier, then apply the changes the user approves. Use when the user asks to categorize, recategorize, check new transactions, or recheck categories of a period or an account in Zenmoney.
compatibility: Runs in Claude Code only, because it needs the Workflow tool and the agents of the plugin zenmoney-cleaner.
---

# Categorize or recheck categories

You run these steps in order and decide nothing the steps do not name. Code does every step that has 1 right answer; agents do the judging; the user decides every change.

`<cli>` stands for `PYTHONPATH="${CLAUDE_PLUGIN_ROOT}" python3 -m zenmoney_cleaner`, `<out>` for a new folder `<run>/<mode>-<short name>`, and `<args>` for `--snapshot <run>/snapshot.json --out <out>`. `<home>` is the folder that `<cli> home` prints; every command finds it the same way by itself and prints it. Where it finds none, run the setup skill of zenmoney-cleaner first. It holds `config.yml`, `policy.md`, `verified.yml` and `places.yml`.

## 1. Scope

Turn the request into a scope:

| The user asks | Mode | Options |
|---|---|---|
| categorize what has no category | `without-category` | usually none |
| check the new transactions | `new-in-zenmoney`, the transactions Zenmoney shows as New | usually none |
| recheck a period, an account, spendings | `recheck-all`, with or without a category | `--from`, `--to`, `--account`, `--type` |

`--from` and `--to` take a day as `YYYY-MM-DD` or a month as `YYYY-MM`, which means its first or its last day, so "August to October" is `--from 2026-08 --to 2026-10`, and "the last 3 months" runs from the same day 3 months ago to today. `--account` takes an account name as Zenmoney shows it and repeats for several; `--type expense` means spendings, `--type income` incomes. Every mode takes these options too. Say the scope back to the user in 1 line before you go on.

The snapshot must cover the scope: use the newest snapshot of the fetch-transactions skill when it does and no change was made in Zenmoney since, and else run the fetch-transactions skill for the scope's period with 3 months before it, because the months before show the categorizer the user's habits.

## 2. Prepare

Run `<cli> prepare <args> --mode <mode>` with the options of the scope. It saves the scope in `<out>`, so the later commands take the same transactions; it decides the strict rules of `config.yml`, skips the transactions that `verified.yml` confirms, and writes the categorize jobs for the rest. Where it stops with an error, show the error and help the user fix the file it names.

## 3. The agent stages

Each stage below is 1 command that writes the jobs of the next stage, and 1 Workflow call that runs them. Where a command prints 0 jobs, skip its Workflow call.

```
Workflow({ name: "zenmoney-cleaner:run-jobs", args: { jobs: "<out>/<stage>/jobs.workflow.js" } })
```

1. Run the Workflow for the stage `categorize`.
2. Run `<cli> route <args>`. It checks the answers and writes the research jobs for the merchants the categorizer was unsure of. A merchant that `places.yml` already holds is not searched again: its job only judges its transactions again with the place found before. Add `--research-again` only where the user asks to search the web again, such as for a place that changed. Run the Workflow for the stage `research`; each of its jobs researches 1 merchant and then judges its transactions again.
3. Run `<cli> verify <args>`. It writes the verify jobs for the proposed changes of categories the user set. Run the Workflow for the stage `verify`.
4. Run `<cli> propose <args>`. It writes `proposal.md`, `proposal.json` and `unknown-merchants.json` into `<out>`.

Where `route`, `verify` or `propose` exits with code 2 and prints `rerun:`, the categorizer answered some jobs wrongly, such as with a misspelled category key or a missing transaction: the command has written those jobs, each with the problems of its last answer, into `jobs-again.workflow.js` of the stage it names. Run the Workflow for that file, then the same command again, without asking the user. After 2 reruns of 1 job the command stops with an error instead; show the error and stop. Where a Workflow result lists failed steps, run that Workflow once more. A merchant whose bank text holds no business name to search, such as a private person's name or a date with a code, goes to the user undecided without research.

## 4. Review with the user

Show the user the 2 tables of `proposal.md` as they stand, with their numbers and their columns `# | Date | Shop | Account | Amount | Comment | Now → New | Why`: first the changes, then the undecided merchants, whose numbers run on after the changes, so the user can answer each row by its number; a shop paid in 2 currencies has 1 row per currency, because amounts of different currencies never add up. In an undecided row, `Now → New` ends in the most probable category with a `?`, such as `Work → Sport & Hobby?`, or only `?` where nobody guessed; it is a suggestion, which applies only where the user names that row. Show every row of both tables, and give the confirmed ones only as a count. Below the tables, name the rows whose current category looks wrong to you, by their numbers, and ask the user to answer by number: apply or keep for a change, and a category or keep for an undecided merchant; a row the user does not name keeps its current category. For each group the user corrects, ask whether it is a rule for the future; write such a rule in words into `<home>/policy.md`, or, for a place only the user knows, as a line under *Places only I know*. Where the user changed `policy.md`, run step 2 again.

## 5. Approve and apply

Agree on the lowest confidence to apply, the merchant keys to leave undecided (`--skip`), the merchant keys whose current category the user confirms (`--keep`), and the merchant keys the user gives a category of their own (`--set "<merchant key>=<category key>"`, with a key of `config.yml`); `--keep` and `--set` work on changes and on undecided merchants alike. Then run `<cli> approve --proposal <out>/proposal.json --min-confidence <high|medium|low> --skip <key> --keep <key> --set "<key>=<category key>" --out <out>/batches.json`. It writes the batches and records every approved, kept and confirmed category with its reason in `verified.yml`, which later runs show the categorizer as examples. In the mode `new-in-zenmoney` the batches also mark the confirmed transactions reviewed, so they leave the New list of Zenmoney; every update marks its transaction reviewed anyway. Run it only after the user approved, because it records the approval.

Send each list of `upsertBatches` to `upsert_transactions` in order. Before any list of `deleteBatches`, show the user the transactions it deletes and get a yes for that deletion, because Zenmoney cannot restore a deleted transaction; then send it to `delete_transactions`. Append each result to `<out>/applied.json`, so a stopped run resumes at the first batch with no result. Report what changed, and suggest a new fetch before the next run.
