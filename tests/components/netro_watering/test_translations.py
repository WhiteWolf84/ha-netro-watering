"""Guard the translation files against drifting apart from strings.json.

`strings.json` is the source of truth Home Assistant renders the config and options
flows from; every shipped locale -- including `en.json`, which is the fallback for
any locale that lacks a key -- must expose exactly the same set of keys. A missing
key does not raise: the UI simply renders a field with no label, which is why this
needs a test rather than review.
"""

import json
from pathlib import Path

import pytest

COMPONENT_DIR = Path(__file__).parents[3] / "custom_components" / "netro_watering"
STRINGS_FILE = COMPONENT_DIR / "strings.json"
TRANSLATIONS_DIR = COMPONENT_DIR / "translations"

TRANSLATION_FILES = sorted(TRANSLATIONS_DIR.glob("*.json"))


def _flatten(node, prefix=""):
    """Return every dotted key path contained in a nested translation mapping."""
    keys = set()
    for key, value in node.items():
        path = f"{prefix}{key}"
        keys.add(path)
        if isinstance(value, dict):
            keys |= _flatten(value, f"{path}.")
    return keys


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_translation_files_exist() -> None:
    """At least the English fallback must ship."""
    assert TRANSLATION_FILES, "no translation files found"
    assert (TRANSLATIONS_DIR / "en.json").exists()


@pytest.mark.parametrize("translation_file", TRANSLATION_FILES, ids=lambda p: p.name)
def test_translation_matches_strings(translation_file: Path) -> None:
    """Each locale exposes exactly the keys declared in strings.json."""
    expected = _flatten(_load(STRINGS_FILE))
    actual = _flatten(_load(translation_file))

    missing = sorted(expected - actual)
    extra = sorted(actual - expected)

    assert not missing, f"{translation_file.name} is missing keys: {missing}"
    assert not extra, f"{translation_file.name} has unknown keys: {extra}"


@pytest.mark.parametrize("translation_file", TRANSLATION_FILES, ids=lambda p: p.name)
def test_translation_values_are_non_empty(translation_file: Path) -> None:
    """A blank string renders as an unlabelled field, so treat it as missing."""

    def walk(node, prefix=""):
        for key, value in node.items():
            path = f"{prefix}{key}"
            if isinstance(value, dict):
                walk(value, f"{path}.")
            else:
                assert isinstance(value, str) and value.strip(), (
                    f"{translation_file.name}: '{path}' is empty"
                )

    walk(_load(translation_file))
