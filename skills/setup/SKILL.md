---
name: setup
description: Set up zenmoney-cleaner on its first run, by creating the home folder for its settings and history with the user's own Zenmoney categories, country and first rules. Use when another zenmoney-cleaner skill finds no home folder, or when the user asks to set up or start over with zenmoney-cleaner.
---

# Set up the home folder

`<cli>` stands for `PYTHONPATH="${CLAUDE_PLUGIN_ROOT}" python3 -m zenmoney_cleaner`.

1. Run `<cli> home`. Where it prints a folder, the setup is done: tell the user the folder and go back to the skill that sent you here.
2. Ask the user 1 question: keep the settings and history for their user account, which works from any folder (recommended), or in this folder, for this project only. `<cli> home` printed the path of each. Where nobody can answer, take the user account.
3. Call `list_categories` and save the reply as `categories.json` in a new temporary folder outside the project, as the fetch-transactions skill saves its pages: copy a saved file with `cp`, or write an inline reply with the Write tool, exactly as returned.
4. Ask the user for their country and, optionally, their home city; work out the 2-letter code of the country yourself.
5. Run `<cli> init --place <project|user-account> --categories <categories.json> --country "<country>" --country-code <code>`, with `--city "<city>"` where the user named one. It creates the folder with a `config.yml` that holds a key for every Zenmoney category except the balance-adjustment one, and the example `policy.md`. Delete the temporary folder.
6. Show the user the category keys of `config.yml`, and remove the categories they say the agents must never pick.
7. Ask the user for 2 or 3 rules of how they categorize, in their own words, such as which category a shop they often visit belongs to, or what a category holds for them. Write them into `policy.md` in place of its example rules, and remove the example line under *Places only I know*.
8. Tell the user the full path of the folder, and that they can change any rule or setting by asking Claude. Then go back to the skill that sent you here.
