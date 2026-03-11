#!/usr/bin/env python3
"""
jlpt.py

Parse JLPT word lists (CSV files per level) and build a lookup mapping.
Source: https://github.com/elzup/jlpt-word-list

Each CSV has columns: expression, reading, meaning, tags
"""

import csv
import sys
import unicodedata
from pathlib import Path
from typing import Optional

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import JLPT_DIR

# JLPT levels in order from easiest to hardest
JLPT_LEVELS = ["N5", "N4", "N3", "N2", "N1"]

# Map from filename to level
_LEVEL_FILES = {
    "n5.csv": "N5",
    "n4.csv": "N4",
    "n3.csv": "N3",
    "n2.csv": "N2",
    "n1.csv": "N1",
}


def _normalize_kana(text: str) -> str:
    """Normalize kana reading to standard NFKC form."""
    return unicodedata.normalize("NFKC", text)


def parse_jlpt_words(
    jlpt_dir: Path = JLPT_DIR,
) -> dict[tuple[str, str], str]:
    """
    Parse all JLPT word list CSVs and return a mapping.

    Words appearing in multiple levels are assigned the easiest (highest N)
    level, since that's typically the more common/basic usage.

    Args:
        jlpt_dir: Directory containing n1.csv through n5.csv

    Returns:
        Dict mapping (expression, reading) -> jlpt_level (e.g. "N5")
    """
    lookup: dict[tuple[str, str], str] = {}

    # Process from hardest to easiest so easier levels overwrite
    for filename in ["n1.csv", "n2.csv", "n3.csv", "n4.csv", "n5.csv"]:
        level = _LEVEL_FILES[filename]
        filepath = jlpt_dir / filename

        if not filepath.exists():
            print(f"  Warning: {filepath} not found, skipping {level}")
            continue

        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                expression = row.get("expression", "").strip()
                reading = _normalize_kana(row.get("reading", "").strip())

                if not expression or not reading:
                    continue

                lookup[(expression, reading)] = level

    return lookup


def parse_jlpt_expressions(
    jlpt_dir: Path = JLPT_DIR,
) -> dict[str, str]:
    """
    Parse JLPT word lists and return a simplified mapping by expression only.

    When the same expression appears at multiple levels, the easiest level wins.

    Args:
        jlpt_dir: Directory containing n1.csv through n5.csv

    Returns:
        Dict mapping expression -> jlpt_level
    """
    lookup: dict[str, str] = {}

    for filename in ["n1.csv", "n2.csv", "n3.csv", "n4.csv", "n5.csv"]:
        level = _LEVEL_FILES[filename]
        filepath = jlpt_dir / filename

        if not filepath.exists():
            continue

        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                expression = row.get("expression", "").strip()
                if expression:
                    lookup[expression] = level

    return lookup


if __name__ == "__main__":
    print(f"Parsing JLPT word lists from {JLPT_DIR}...")
    words = parse_jlpt_words()
    print(f"Found {len(words)} unique (expression, reading) pairs")

    # Count by level
    by_level: dict[str, int] = {}
    for _, level in words.items():
        by_level[level] = by_level.get(level, 0) + 1

    for level in JLPT_LEVELS:
        print(f"  {level}: {by_level.get(level, 0)} words")

    # Show some examples
    print("\nExample entries:")
    for (expr, reading), level in list(words.items())[:10]:
        print(f"  {expr} ({reading}) -> {level}")
