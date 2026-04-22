#!/usr/bin/env python3
"""
compare_grapheme_kanji_names.py

For every (grapheme, kanji) pair that share a symbol, check whether the
grapheme's name (or any of its nameAliases) is a "subset" of the kanji's
primary meanings. Report every pair where it is NOT.

"Subset" is interpreted loosely: a grapheme name is considered to match a
kanji's meanings if, case-insensitively, the grapheme name is a substring of
any primary meaning, or any primary meaning is a substring of the grapheme
name. nameAliases are also considered — if any alias matches, the pair is
treated as a match.

Primary symbol is used for matching (grapheme variants are not cross-checked
against kanji symbols here; variants are tracked separately in the grapheme-
variant-group model).

Output: japanese/docs/reports/grapheme-kanji-name-mismatches.txt
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import GRAPHEME_DOCS, KANJI_DOCS, REPORTS_DIR
from lib.grapheme_io import load_graphemes


OUTPUT_PATH = REPORTS_DIR / "grapheme-kanji-name-mismatches.txt"


def load_kanji(docs_dir: Path = KANJI_DOCS) -> dict[str, dict]:
    """Load all kanji documents keyed by $id."""
    kanji: dict[str, dict] = {}
    for json_file in docs_dir.glob("*.json"):
        with open(json_file, "r", encoding="utf-8") as f:
            doc = json.load(f)
            kanji[doc["$id"]] = doc
    return kanji


def _normalize(text: str) -> str:
    return text.strip().lower()


def names_match_meanings(names: list[str], meanings: list[str]) -> bool:
    """
    True iff any name is a substring of any meaning (or vice versa), case-
    insensitive. Empty inputs always return False.
    """
    norm_names = [_normalize(n) for n in names if n and n.strip()]
    norm_meanings = [_normalize(m) for m in meanings if m and m.strip()]
    if not norm_names or not norm_meanings:
        return False
    for n in norm_names:
        for m in norm_meanings:
            if n == m or n in m or m in n:
                return True
    return False


def main():
    print("Grapheme/Kanji Shared-Symbol Name Comparison")
    print("=" * 44)

    print("\n1. Loading graphemes…")
    graphemes = load_graphemes()
    print(f"   {len(graphemes)} grapheme documents")

    print("\n2. Loading kanji…")
    kanji = load_kanji()
    print(f"   {len(kanji)} kanji documents")

    # Build symbol -> kanji lookup (primary symbol only)
    kanji_by_symbol: dict[str, dict] = {}
    for doc in kanji.values():
        symbol = doc.get("symbol")
        if symbol:
            kanji_by_symbol[symbol] = doc

    shared: list[tuple[dict, dict]] = []
    for g in graphemes.values():
        symbol = g.get("symbol")
        if not symbol:
            continue
        k = kanji_by_symbol.get(symbol)
        if k is not None:
            shared.append((g, k))

    print(f"\n3. Found {len(shared)} grapheme/kanji pairs sharing a primary symbol.")

    mismatches: list[tuple[dict, dict]] = []
    for g, k in shared:
        grapheme_names = [g.get("name", "")] + list(g.get("nameAliases", []) or [])
        kanji_meanings = list(k.get("meanings", []) or [])
        if not names_match_meanings(grapheme_names, kanji_meanings):
            mismatches.append((g, k))

    print(f"\n4. Mismatches (grapheme name not a subset of kanji primary meanings): {len(mismatches)}")

    mismatches.sort(key=lambda pair: (pair[0].get("strokeCount") or 999, pair[0].get("unicode", "")))

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write("Grapheme / Kanji Shared-Symbol Name Mismatches\n")
        f.write("=" * 48 + "\n\n")
        f.write(
            "Pairs where a grapheme and kanji share the same primary symbol\n"
            "AND the grapheme's name/aliases are NOT a (loose substring) subset\n"
            "of the kanji's primary `meanings`. Also listed: kanji secondary\n"
            "meanings for reviewer context.\n\n"
        )
        f.write(f"Total shared-symbol pairs : {len(shared)}\n")
        f.write(f"Total mismatches reported : {len(mismatches)}\n\n")
        f.write("-" * 48 + "\n\n")

        for g, k in mismatches:
            symbol = g.get("symbol", "?")
            unicode_id = g.get("unicode", "")
            strokes = g.get("strokeCount", "?")
            g_name = g.get("name", "")
            g_aliases = g.get("nameAliases", []) or []
            k_meanings = k.get("meanings", []) or []
            k_secondary = k.get("secondaryMeanings", []) or []

            f.write(f"{symbol}  ({unicode_id}, {strokes} strokes)\n")
            f.write(f"  grapheme name    : {g_name}\n")
            if g_aliases:
                f.write(f"  grapheme aliases : {', '.join(g_aliases)}\n")
            f.write(f"  kanji meanings   : {', '.join(k_meanings) if k_meanings else '(none)'}\n")
            if k_secondary:
                f.write(f"  kanji secondary  : {', '.join(k_secondary)}\n")
            f.write(f"  grapheme $id     : {g.get('$id', '')}\n")
            f.write(f"  kanji $id        : {k.get('$id', '')}\n")
            f.write("\n")

    print(f"\nWritten {len(mismatches)} mismatches to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
