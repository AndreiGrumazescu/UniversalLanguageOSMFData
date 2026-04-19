#!/usr/bin/env python3
"""
002_kunyomi_to_hiragana.py

Sweep 'kunyomi' and 'secondaryKunyomi' readings to hiragana across all kanji
documents. kunyomi is documented as hiragana by the schema, but a handful of
docs carry katakana loan-word readings (e.g., デシメートル on kanji:U+7C89).
This migration enforces the schema by mechanical char-offset conversion,
matching migration 001's treatment of onyomi.
"""

import sys
from pathlib import Path

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.normalizers import katakana_to_hiragana
from lib.paths import KANJI_DIR, KANJI_DOCS
from migrations._runner import run_cli


NUMBER = 2
SLUG = "kunyomi_to_hiragana"
GOAL = "Sweep kunyomi and secondaryKunyomi to hiragana (catches stray loan-word katakana)."
TARGET_DIR = KANJI_DOCS
SCHEMA_PATH = KANJI_DIR / "japanese-kanji.schema.json"


def preflight(schema: dict) -> str | None:
    """Verify the schema already describes kunyomi as hiragana."""
    props = schema.get("schema", {}).get("properties", {})
    for field in ("kunyomi", "secondaryKunyomi"):
        desc = props.get(field, {}).get("description", "")
        if "hiragana" not in desc.lower():
            return (
                f"schema description for '{field}' does not mention 'hiragana' "
                f"(got: {desc!r})."
            )
    return None


def _has_leftover_katakana(text: str) -> bool:
    """Any char in U+30A0-U+30FF other than U+30FC (ー) is unexpected."""
    return any(0x30A0 <= ord(c) <= 0x30FF and ord(c) != 0x30FC for c in text)


def transform(doc: dict) -> dict:
    for field in ("kunyomi", "secondaryKunyomi"):
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
