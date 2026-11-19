# zenmoney-cleaner

A Claude Code plugin that cleans up Zenmoney data through the Zenmoney connector. It categorizes transactions with agents that follow your own rules in words and research unknown places on the web, and it removes the balance corrections that a bank sync stacks up. Every change is proposed first and applied only after you approve it, and every deletion is shown to you again before it is sent.

## Install

1. Connect the Zenmoney connector in Claude Code.
2. Run `/plugin marketplace add <path or URL of this repository>` and `/plugin install zenmoney-cleaner`, then start a new session.
3. Python 3.10 or newer with PyYAML must be on the path (`pip install PyYAML`).

## Use

Ask Claude in your own words:

- "Fetch my Zenmoney transactions for the last 3 months."
- "Categorize everything that has no category."
- "Check my new transactions" — the ones Zenmoney shows as New.
- "Recheck the spendings of the account Card from August to October."
- "Clean up the balance corrections."

The first fetch copies `config.example/` into `local/` of your project. Name your categories and your strict rules in `config.yml`, and write how you categorize in `policy.md`; [docs/configuration.md](docs/configuration.md) explains each file.

## Cost

Categorizing runs Haiku on batches of up to 120 transactions, and Sonnet only for places the categorizer is unsure of and for changes of a category you set. Every agent of a stage starts with the same instructions, so they are read from the prompt cache after the first call.

## Development

Run the tests with `pip install -e '.[test]'` and `python3 -m pytest -q`.

## License

MIT, see [LICENSE](LICENSE).
