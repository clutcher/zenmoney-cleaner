# Configuration

The home folder holds your settings and history. Every command takes the first of these that it finds, and never merges 2 of them:

1. The folder of the option `--home`.
2. The folder of the variable `$ZENMONEY_CLEANER_HOME`.
3. `zenmoney-cleaner/` in the current folder or the nearest folder above it, where it holds `config.yml`: project mode, for this project only, which also works from a run folder inside it.
4. `zenmoney-cleaner/` in the config folder of your user account, where it holds `config.yml`, which works from any folder: `$XDG_CONFIG_HOME` or `~/.config` on Linux, `~/Library/Application Support` on macOS, `%APPDATA%` on Windows.

`python3 -m zenmoney_cleaner home` prints the folder found, or the 2 places where the first run can create it. Every command prints the folder it used. In project mode, keep `zenmoney-cleaner/` out of version control, because it holds your own rules and data.

| File | Holds | Written by |
|---|---|---|
| `config.yml` | location, category keys, bank text cleanup, strict rules, correction settings | you |
| `policy.md` | how you categorize, in words, and the places only you know | you, helped by the skill |
| `policy-candidates.md` | rules you may need later; no agent reads it | you |
| `verified.yml` | the confirmed category of each transaction, with its reason | the command `approve` |
| `history.json` | a few fields of each transaction of the last 13 months, and the day of the last check | the command `merge` and the command `approve` |
| `places.yml` | what kind of place each researched merchant is, with its source and trust | the command `verify`, from the research answers |
| `data/` | the fetched snapshots and the files of each run | the skills |

## config.yml

`location` is your country and its 2-letter code, both required, and your home city, which you may leave out. The researcher searches there, and in the business register of that country, when a bank text names no city.

`categories` maps a short key to the name of a Zenmoney category, exactly as Zenmoney shows it; a subcategory may be written with its parent, such as `Food / Cafes`. The setup writes every category of your Zenmoney here. The rules and the agents answer with the keys. A name that Zenmoney does not have stops every command, so a renamed category in Zenmoney shows up at once. List every category you want the agents to use, and leave out the ones they must never pick.

`payee.strip` holds regular expressions that remove bank noise from a bank text, such as a country tail, a city or a store number. The payments of 1 merchant then group together, and the agents judge them as 1 place.

`rules` holds only strict cases, which code decides without an agent; the first rule that matches decides. A rule matches on `payee` (exact bank texts after `strip`, case ignored, 1 text or a list), `comment` (fragments, case ignored, 1 or a list), `account` (an account name) and `type` (`expense` or `income`), and every key it names must hold. Its action is `categorize` with `category: <key>` (the default), `delete`, or `transfer` with `to_account: <account name>`, and `reason` says why in the proposal. Anything that needs judgment goes into `policy.md` instead.

`history.overlap_days`, 7 by default, is how many days before the newest day of `history.json` each fetch starts, so payments that the bank posts days later with an earlier date are fetched; raise it for a bank that posts up to 60 days late.

`corrections.match_window_days` is how many days before a balance correction a pending purchase may be dated, and `corrections.max_match_size` the most transactions that 1 correction is matched against. `corrections.adjustment_category` is optional: the name of your balance-adjustment category, used instead of the id that Zenmoney reports; the corrections skill writes it when Zenmoney reports none.

## policy.md

Rules in words, written as you would explain them to a person, and a section *Places only I know* for names the web cannot explain. The categorizer and the verifier read it on every call, so its rules win over the agents' own idea of a category. Write only your own choices, the ones a stranger would get wrong; the agents already know common places. Where you are unsure whether the agents need a rule, keep it in `policy-candidates.md`, and move it here once a run gets that case wrong.

## history.json

The id, date, kind, account, bank text, amount and category of each transaction of the last 13 months, so a later run fetches only the new days and still shows the categorizer what you chose before and which payments repeat each month. Each fetch replaces the days it covered, so a transaction deleted or changed in Zenmoney is gone or changed here too. History only gives hints: no run proposes a change of a transaction that the fresh fetch does not hold. `last_check` is the newest day of the last categorize run you approved, or the day of the oldest row you left open in it, so a skipped or undecided row comes back next time; the mode `since-last-check` starts there, that day included, and skips the transactions already confirmed. Delete the file to start over with a fetch of 3 months.

## places.yml

Each merchant key the researcher looked up, with `place`, `source`, `trust` and the day `researched`. A later run judges such a merchant with this finding instead of searching the web again, so a wider period or another account costs no new research for the merchants already seen. Delete an entry, or run `route` with `--research-again`, to search a place again.

## verified.yml

1 entry per transaction id with the category, who confirmed it, the reason, the date, the amount, the bank text, and the comment the user added at the approval, if any. A run skips a transaction whose category still equals the confirmed one, and the newest 300 distinct bank texts go into every categorize task as examples, so a new branch of a known chain is decided by analogy. Delete an entry to have that transaction judged again.

## The balance-adjustment category

Never rename the category that Zenmoney uses for balance corrections, whose name depends on the language of your Zenmoney, and never create a second category of the same name: the connector then reports its id `balanceAdjustmentCategoryId` as null, because it finds the category missing or ambiguous. The plugin reads that id, or the name in `corrections.adjustment_category` where you set one, and never changes the category itself.
