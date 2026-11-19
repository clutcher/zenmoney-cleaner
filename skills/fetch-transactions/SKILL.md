---
name: fetch-transactions
description: Download Zenmoney transactions for a date range into a local snapshot that the other zenmoney-cleaner skills read. Use before categorize or corrections, or when the user asks to fetch, download or refresh their Zenmoney data.
---

# Fetch a snapshot

The other skills never call Zenmoney for data themselves; they read the snapshot this skill writes, so every proposal rests on 1 fixed copy of the data.

## Steps

1. Run `PYTHONPATH="${CLAUDE_PLUGIN_ROOT}" python3 -m zenmoney_cleaner home`; `<home>` is the folder it prints. Where it finds none, run the setup skill of zenmoney-cleaner first.
2. Agree on the date range with the user, and create the run folder `<home>/data/<today>-<short name>/` with a `pages/` folder inside. For the corrections skill, also create `correction-pages/`.
3. Call `list_transactions` with `from`, `to` and `limit: 200`, and follow `nextCursor` until it is null. Save every page as `pages/page-001.json`, `page-002.json` and so on, in order:
   - A page too large for the reply arrives as a saved file whose path the tool result names; copy that file with `cp`, so no character of it changes.
   - A page that arrives inline is written with the Write tool, exactly as returned.
4. Save the replies of `list_categories` and `list_accounts` as `categories.json` and `accounts.json` in the run folder, the same way.
5. For the corrections skill, also page `list_transactions` with `categoryIds: [<the id of the category that corrections.adjustment_category of config.yml names, else balanceAdjustmentCategoryId of categories.json>]`, `from: 2000-01-01`, `to: <today>` and `limit: 200` into `correction-pages/` the same way, because a correction chain can start years before the date range.
6. Run the merge, with a second `--pages <run>/correction-pages` where step 5 ran:

   ```
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}" python3 -m zenmoney_cleaner merge --pages <run>/pages --categories <run>/categories.json --accounts <run>/accounts.json --out <run>/snapshot.json --history <home>/history.json --fetched-from <from of step 3> --fetched-to <to of step 3>
   ```

   Each `--pages` folder holds the pages of 1 query, and a transaction that 2 queries return is kept once. The fetched range replaces that range in `history.json`, and its earlier months join the snapshot as history, which the categorizer sees as the user's habits but which no run changes. The merge stops with an error when no page of a folder ends its cursor chain; then a page is missing, so fetch that query again.
7. Tell the user the run folder and the count of transactions.

Fetch again after the user changes data in Zenmoney, because a proposal built on an old snapshot proposes changes that are already done.
