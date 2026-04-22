#!/usr/bin/env python3
"""
verify_shared_symbol_dependency.py

For every (grapheme, kanji) pair that share a primary symbol, verify that the
kanji's kanji-grapheme-dependency document lists the same-symbol grapheme as
one of its components. Report every pair where the dependency is missing.

Rationale: a kanji that also exists as a standalone grapheme (same codepoint,
same primary symbol) should depend on that grapheme — otherwise the
decomposition graph is inconsistent.

Output: japanese/docs/reports/kanji-missing-self-grapheme-dependency.txt
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import KANJI_DOCS, KANJI_GRAPHEME_DEP_DOCS, REPORTS_DIR
from lib.grapheme_io import load_graphemes


OUTPUT_PATH = REPORTS_DIR / "kanji-missing-self-grapheme-dependency.txt"


def load_kanji(docs_dir: Path = KANJI_DOCS) -> dict[str, dict]:
    """Load all kanji documents keyed by $id."""
    kanji: dict[str, dict] = {}
    for json_file in docs_dir.glob("*.json"):
        with open(json_file, "r", encoding="utf-8") as f:
            doc = json.load(f)
            kanji[doc["$id"]] = doc
    return kanji


def load_kanji_grapheme_deps(
    docs_dir: Path = KANJI_GRAPHEME_DEP_DOCS,
) -> dict[str, list[str]]:
    """
    Load kanji-grapheme-dependency documents.

    Returns:
        Dict mapping parent kanji $id -> list of component grapheme $ids.
    """
    deps: dict[str, list[str]] = {}
    for json_file in docs_dir.glob("*.json"):
        with open(json_file, "r", encoding="utf-8") as f:
            doc = json.load(f)
        parent_id = doc["connectors"]["parent"]["$id"]
        components: list[str] = []
        seen: set[str] = set()
        for item in doc.get("many", []):
            cid = item["connectors"]["component"]["$id"]
            if cid not in seen:
                seen.add(cid)
                components.append(cid)
        deps[parent_id] = components
    return deps


def main():
    print("Kanji → Shared-Symbol Grapheme Dependency Check")
    print("=" * 48)

    print("\n1. Loading graphemes…")
    graphemes = load_graphemes()
    print(f"   {len(graphemes)} grapheme documents")

    print("\n2. Loading kanji…")
    kanji = load_kanji()
    print(f"   {len(kanji)} kanji documents")

    print("\n3. Loading kanji-grapheme dependencies…")
    deps = load_kanji_grapheme_deps()
    print(f"   {len(deps)} dependency documents")

    # Build symbol -> kanji lookup (primary symbol only)
    kanji_by_symbol: dict[str, dict] = {}
    for doc in kanji.values():
        symbol = doc.get("symbol")
        if symbol:
            kanji_by_symbol[symbol] = doc

    # Enumerate shared-symbol pairs
    shared: list[tuple[dict, dict]] = []
    for g in graphemes.values():
        symbol = g.get("symbol")
        if not symbol:
            continue
        k = kanji_by_symbol.get(symbol)
        if k is not None:
            shared.append((g, k))

    print(f"\n4. Found {len(shared)} grapheme/kanji pairs sharing a primary symbol.")

    missing: list[tuple[dict, dict, list[str]]] = []
    missing_dep_doc: list[tuple[dict, dict]] = []

    for g, k in shared:
        kanji_id = k.get("$id", "")
        grapheme_id = g.get("$id", "")
        components = deps.get(kanji_id)
        if components is None:
            missing_dep_doc.append((g, k))
            continue
        if grapheme_id not in components:
            missing.append((g, k, components))

    print(
        f"\n5. Missing self-grapheme dependency : {len(missing)}"
        f"  |  No dependency doc at all : {len(missing_dep_doc)}"
    )

    def sort_key(triple):
        g = triple[0]
        return (g.get("strokeCount") or 999, g.get("unicode", ""))

    missing.sort(key=sort_key)
    missing_dep_doc_sorted = sorted(
        missing_dep_doc,
        key=lambda pair: (pair[0].get("strokeCount") or 999, pair[0].get("unicode", "")),
    )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write("Kanji Missing Self-Grapheme Dependency\n")
        f.write("=" * 40 + "\n\n")
        f.write(
            "Pairs where a grapheme and kanji share the same primary symbol\n"
            "but the kanji's kanji-grapheme-dependency document does NOT list\n"
            "that grapheme as one of its components.\n\n"
        )
        f.write(f"Total shared-symbol pairs       : {len(shared)}\n")
        f.write(f"Kanji with no dependency doc    : {len(missing_dep_doc_sorted)}\n")
        f.write(f"Kanji missing self-grapheme dep : {len(missing)}\n\n")
        f.write("-" * 40 + "\n\n")

        if missing_dep_doc_sorted:
            f.write("A) Kanji that have NO kanji-grapheme-dependency document:\n\n")
            for g, k in missing_dep_doc_sorted:
                symbol = g.get("symbol", "?")
                unicode_id = g.get("unicode", "")
                strokes = g.get("strokeCount", "?")
                f.write(f"{symbol}  ({unicode_id}, {strokes} strokes)\n")
                f.write(f"  grapheme $id : {g.get('$id', '')}\n")
                f.write(f"  kanji $id    : {k.get('$id', '')}\n\n")
            f.write("-" * 40 + "\n\n")

        if missing:
            f.write("B) Kanji whose dependency doc omits the same-symbol grapheme:\n\n")
            for g, k, components in missing:
                symbol = g.get("symbol", "?")
                unicode_id = g.get("unicode", "")
                strokes = g.get("strokeCount", "?")
                f.write(f"{symbol}  ({unicode_id}, {strokes} strokes)\n")
                f.write(f"  grapheme $id     : {g.get('$id', '')}\n")
                f.write(f"  kanji $id        : {k.get('$id', '')}\n")
                f.write(
                    f"  current components ({len(components)}): "
                    f"{', '.join(components) if components else '(none)'}\n\n"
                )

    print(f"\nWritten report to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
