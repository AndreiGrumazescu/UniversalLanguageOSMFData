#!/usr/bin/env python3
"""
003_strip_okurigana.py

Strip okurigana from kanji readings. In kanjidic2 convention a period in a
kunyomi entry separates the kanji's own reading from the trailing kana
(okurigana) that accompanies it in verb/adjective forms — e.g.,
'はさ.む' means the kanji reads はさ with okurigana む (as in 挟む, "to pinch").

The kanji document is about the kanji's reading only, not about the words
that use it, so everything from the period onward is dropped.

Secondary fallout:
  - Stripping okurigana can produce duplicate readings within a single array
    (e.g., 'う.つ' and 'う.ち' both collapse to 'う'). Dedupe in place.
  - A secondary reading may now match a primary reading. Drop any such
    duplicates from the secondary array. If the secondary array becomes
    empty, remove the field entirely.
"""

import sys
from pathlib import Path

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import KANJI_DIR, KANJI_DOCS
from migrations._runner import run_cli


NUMBER = 3
SLUG = "strip_okurigana"
GOAL = "Strip everything after '.' in reading entries; dedupe within and across primary/secondary."
TARGET_DIR = KANJI_DOCS
SCHEMA_PATH = KANJI_DIR / "japanese-kanji.schema.json"


READING_FIELDS = ("onyomi", "secondaryOnyomi", "kunyomi", "secondaryKunyomi")
PRIMARY_SECONDARY = (("onyomi", "secondaryOnyomi"), ("kunyomi", "secondaryKunyomi"))


def _strip_okurigana(reading: str) -> str:
    return reading.split(".", 1)[0]


def _dedupe(readings: list[str]) -> list[str]:
    """Remove duplicates while preserving first-seen order."""
    return list(dict.fromkeys(readings))


def transform(doc: dict) -> dict:
    # Strip the okurigana suffix from every reading.
    for field in READING_FIELDS:
        if field in doc:
            doc[field] = [_strip_okurigana(r) for r in doc[field]]

    # Dedupe within each array.
    for field in READING_FIELDS:
        if field in doc:
            doc[field] = _dedupe(doc[field])

    # Drop secondary entries that now duplicate a primary reading.
    for primary, secondary in PRIMARY_SECONDARY:
        if primary in doc and secondary in doc:
            primary_set = set(doc[primary])
            doc[secondary] = [r for r in doc[secondary] if r not in primary_set]

    # Remove secondary fields that were emptied by deduplication.
    for _, secondary in PRIMARY_SECONDARY:
        if secondary in doc and not doc[secondary]:
            del doc[secondary]

    return doc


if __name__ == "__main__":
    run_cli(sys.modules[__name__])
