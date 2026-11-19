from pathlib import Path

_REPOSITORY_FOLDER = Path(__file__).resolve().parents[1]
_SKIPPED_FOLDER_NAMES = {".git", ".pytest_cache", "__pycache__", ".venv", "zenmoney-cleaner"}
_TEXT_SUFFIXES = {".py", ".md", ".yml", ".yaml", ".json", ".js", ".toml", ".txt", ""}


def _list_text_files() -> list[Path]:
    return [
        path
        for path in _REPOSITORY_FOLDER.rglob("*")
        if path.is_file()
        and path.suffix in _TEXT_SUFFIXES
        and not _SKIPPED_FOLDER_NAMES.intersection(path.relative_to(_REPOSITORY_FOLDER).parts)
    ]


def test_should_hold_only_english_letters_when_the_repository_is_public() -> None:
    # when
    non_english_lines = [
        f"{path.relative_to(_REPOSITORY_FOLDER)}:{number}"
        for path in _list_text_files()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if any(character.isalpha() and not character.isascii() for character in line)
    ]

    # then
    assert non_english_lines == []
