#!/usr/bin/env python3
"""
001_onyomi_to_hiragana.py

Convert 'onyomi' and 'secondaryOnyomi' readings in every kanji document
from katakana to hiragana. Kunyomi readings (already hiragana) are untouched.

Source: kanjidic2 supplies on'yomi in katakana by convention. The app treats
readings as a uniform "readings" concept, so a mixed representation is
inconvenient. This migration normalizes to hiragana everywhere.
"""

import sys
from pathlib import Path

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.normalizers import katakana_to_hiragana
from lib.paths import KANJI_DIR, KANJI_DOCS
from migrations._runner import run_cli


NUMBER = 1
SLUG = "onyomi_to_hiragana"
GOAL = "Convert onyomi and secondaryOnyomi from katakana to hiragana."
TARGET_DIR = KANJI_DOCS
SCHEMA_PATH = KANJI_DIR / "japanese-kanji.schema.json"


def preflight(schema: dict) -> str | None:
    """Fail fast if the schema still describes onyomi as katakana."""
    props = schema.get("schema", {}).get("properties", {})
    for field in ("onyomi", "secondaryOnyomi"):
        desc = props.get(field, {}).get("description", "")
        if "hiragana" not in desc.lower():
            return (
                f"schema description for '{field}' does not mention 'hiragana' "
                f"(got: {desc!r}). Update the schema in the same commit."
            )
    return None


def _has_leftover_katakana(text: str) -> bool:
    """Any char in U+30A0-U+30FF other than U+30FC (ー) is unexpected."""
    return any(0x30A0 <= ord(c) <= 0x30FF and ord(c) != 0x30FC for c in text)


def transform(doc: dict) -> dict:
    for field in ("onyomi", "secondaryOnyomi"):
        if field not in doc:
            continue
        converted = [katakana_to_hiragana(r) for r in doc[field]]
        leftovers = [r for r in converted if _has_leftover_katakana(r)]
        if leftovers:
            raise ValueError(
                f"unexpected katakana codepoints remain in {field}: {leftovers}"
            )
        doc[field] = converted
    return doc


if __name__ == "__main__":
    run_cli(sys.modules[__name__])
