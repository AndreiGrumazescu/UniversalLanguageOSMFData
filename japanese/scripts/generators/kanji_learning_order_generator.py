#!/usr/bin/env python3
"""
kanji_learning_order_generator.py

Generates a learning-order document for Japanese kanji.

Ordering criteria:
1. Primary: stroke count ascending
2. Secondary: grapheme readiness ascending — the maximum position (in the
   grapheme learning order) of any grapheme component of this kanji. Lower
   means the user learned all needed graphemes earlier.
3. Tertiary: kanjidic grade ascending (1-6 kyouiku, 8 jouyou, 9-10 jinmeiyou)
4. Quaternary: popularity descending (how often this kanji appears as a
   component in other kanji, from the component-popularity report)
5. Tiebreaker: $id ascending

Validates the resulting order against kanji-to-kanji dependency data and
reports any violations (warns only — the app uses the dependency graph for
gating independently).

Usage:
    python generators/kanji_learning_order_generator.py [--dry-run]
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.kanjidic import parse_kanjidic_full
from lib.normalizers import nfkc_plus
from lib.paths import (
    KANJI_DOCS,
    KANJI_DEP_DOCS,
    KANJI_GRAPHEME_DEP_DOCS,
    LEARNING_ORDER_DOCS,
    POPULARITY_JSON,
)
from lib.grapheme_io import write_json_document


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def codepoint_str(char: str) -> str:
    """Convert a character to 'U+XXXX' format."""
    cp = ord(char)
    if cp > 0xFFFF:
        return f"U+{cp:05X}"
    return f"U+{cp:04X}"


# ---------------------------------------------------------------------------
# Data Loading
# ---------------------------------------------------------------------------

def load_kanji_documents(docs_dir: Path = KANJI_DOCS) -> dict[str, dict]:
    """Load all kanji documents. Returns dict mapping $id -> document."""
    kanji: dict[str, dict] = {}
    for json_file in docs_dir.glob("*.json"):
        with open(json_file, "r", encoding="utf-8") as f:
            doc = json.load(f)
            kanji[doc["$id"]] = doc
    return kanji


def load_kanji_dependencies(
    docs_dir: Path = KANJI_DEP_DOCS,
) -> dict[str, list[str]]:
    """
    Load kanji-to-kanji dependency documents.
    Returns dict mapping parent kanji $id -> [prerequisite kanji $ids].
    """
    deps: dict[str, list[str]] = {}
    for json_file in docs_dir.glob("*.json"):
        with open(json_file, "r", encoding="utf-8") as f:
            doc = json.load(f)
            parent_id = doc["connectors"]["parent"]["$id"]
            prereqs = []
            seen = set()
            for item in doc.get("many", []):
                pid = item["connectors"]["prerequisite"]["$id"]
                if pid not in seen:
                    seen.add(pid)
                    prereqs.append(pid)
            deps[parent_id] = prereqs
    return deps


def load_kanji_grapheme_dependencies(
    docs_dir: Path = KANJI_GRAPHEME_DEP_DOCS,
) -> dict[str, list[str]]:
    """
    Load kanji-to-grapheme dependency documents.
    Returns dict mapping kanji $id -> [grapheme component $ids].
    """
    deps: dict[str, list[str]] = {}
    for json_file in docs_dir.glob("*.json"):
        with open(json_file, "r", encoding="utf-8") as f:
            doc = json.load(f)
            parent_id = doc["connectors"]["parent"]["$id"]
            components = []
            seen = set()
            for item in doc.get("many", []):
                cid = item["connectors"]["component"]["$id"]
                if cid not in seen:
                    seen.add(cid)
                    components.append(cid)
            deps[parent_id] = components
    return deps


def load_grapheme_learning_order(
    docs_dir: Path = LEARNING_ORDER_DOCS,
) -> dict[str, int]:
    """
    Load the grapheme learning order document.
    Returns dict mapping grapheme $id -> position.
    """
    filepath = docs_dir / "japanese-grapheme-learning-order-default.json"
    if not filepath.exists():
        print(f"  WARNING: {filepath} not found. Run learning_order_generator.py first.")
        return {}

    with open(filepath, "r", encoding="utf-8") as f:
        doc = json.load(f)

    positions: dict[str, int] = {}
    for item in doc.get("many", []):
        gid = item["connectors"]["item"]["$id"]
        pos = item["data"]["position"]
        positions[gid] = pos

    return positions


def load_kanjidic_grades() -> dict[str, int]:
    """
    Load kanjidic grade information.
    Returns dict mapping kanji $id -> grade (1-6, 8, 9, 10).
    """
    entries = parse_kanjidic_full()
    grades: dict[str, int] = {}
    for entry in entries:
        if entry.grade is not None:
            normalized = nfkc_plus(entry.literal)
            unicode = codepoint_str(normalized)
            kanji_id = f"kanji:{unicode}"
            if kanji_id not in grades:
                grades[kanji_id] = entry.grade
    return grades


def load_popularity(json_path: Path = POPULARITY_JSON) -> dict[str, int]:
    """
    Load per-kanji popularity from the component-popularity.json report.
    Returns dict mapping kanji $id -> popularity count.
    Includes all kanji (not just graphemes).
    """
    if not json_path.exists():
        print(f"  WARNING: {json_path} not found.")
        return {}

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    popularity: dict[str, int] = {}
    for stroke_group in data.get("by_stroke_count", {}).values():
        for entry in stroke_group:
            char = entry.get("char", "")
            if char:
                normalized = nfkc_plus(char)
                unicode = codepoint_str(normalized)
                kanji_id = f"kanji:{unicode}"
                pop = entry.get("popularity", 0)
                # Keep the higher popularity if there are duplicates
                if kanji_id not in popularity or pop > popularity[kanji_id]:
                    popularity[kanji_id] = pop

    return popularity


# ---------------------------------------------------------------------------
# Grapheme Readiness
# ---------------------------------------------------------------------------

def compute_grapheme_readiness(
    kanji_grapheme_deps: dict[str, list[str]],
    grapheme_positions: dict[str, int],
) -> dict[str, int]:
    """
    Compute grapheme readiness score for each kanji.

    The readiness score is the maximum position of any grapheme component
    in the grapheme learning order. Lower means the user has all needed
    graphemes available earlier.

    Returns:
        Dict mapping kanji $id -> readiness score (max grapheme position).
        Kanji with no grapheme components get -1 (most ready).
    """
    readiness: dict[str, int] = {}
    for kanji_id, grapheme_ids in kanji_grapheme_deps.items():
        max_pos = -1
        for gid in grapheme_ids:
            pos = grapheme_positions.get(gid)
            if pos is not None and pos > max_pos:
                max_pos = pos
        readiness[kanji_id] = max_pos
    return readiness


# ---------------------------------------------------------------------------
# Ordering
# ---------------------------------------------------------------------------

# Default values for missing data — sorts last within each tier
DEFAULT_GRADE = 99
DEFAULT_READINESS = 9999

def compute_order(
    kanji: dict[str, dict],
    readiness: dict[str, int],
    grades: dict[str, int],
    popularity: dict[str, int],
) -> list[str]:
    """
    Compute the final ordered list of kanji $ids.

    Sort key: (strokeCount ASC, graphemeReadiness ASC, grade ASC,
               popularity DESC, $id ASC)
    """
    sort_entries: list[tuple[tuple, str]] = []

    for kid, doc in kanji.items():
        stroke_count = doc.get("strokeCount", 999)
        ready = readiness.get(kid, DEFAULT_READINESS)
        grade = grades.get(kid, DEFAULT_GRADE)
        pop = popularity.get(kid, 0)

        sort_key = (stroke_count, ready, grade, -pop, kid)
        sort_entries.append((sort_key, kid))

    sort_entries.sort(key=lambda x: x[0])
    return [kid for _, kid in sort_entries]


# ---------------------------------------------------------------------------
# Dependency Validation
# ---------------------------------------------------------------------------

def validate_order(
    ordered: list[str],
    deps: dict[str, list[str]],
    kanji: dict[str, dict],
) -> list[str]:
    """
    Validate that the ordering respects kanji-to-kanji dependency constraints.
    Returns list of violation descriptions (empty if valid).
    """
    position: dict[str, int] = {kid: i for i, kid in enumerate(ordered)}
    violations: list[str] = []

    for parent_id, prereq_ids in deps.items():
        parent_pos = position.get(parent_id)
        if parent_pos is None:
            continue

        parent_doc = kanji.get(parent_id, {})
        parent_symbol = parent_doc.get("symbol", "?")

        for prereq_id in prereq_ids:
            prereq_pos = position.get(prereq_id)
            if prereq_pos is None:
                continue

            if prereq_pos >= parent_pos:
                prereq_doc = kanji.get(prereq_id, {})
                prereq_symbol = prereq_doc.get("symbol", "?")
                violations.append(
                    f"  {prereq_symbol} ({prereq_id}) at pos {prereq_pos} "
                    f"should come before {parent_symbol} ({parent_id}) at pos {parent_pos}"
                )

    return violations


# ---------------------------------------------------------------------------
# Document Generation
# ---------------------------------------------------------------------------

def create_learning_order_document(ordered: list[str]) -> dict:
    """Create a learning-order OSMF document for kanji."""
    return {
        "$schema": "../../../../shared-models/learning-order.schema.json",
        "$id": "japanese-kanji-learning-order-default",
        "connectors": {
            "item": {}
        },
        "data": {
            "contentType": "kanji",
            "trackId": "default",
            "trackName": "Default Kanji Order",
            "source": "Generated: stroke count ASC, grapheme readiness ASC, kanjidic grade ASC, popularity DESC, $id ASC."
        },
        "many": [
            {
                "connectors": {
                    "item": {
                        "$id": kid
                    }
                },
                "data": {
                    "position": i
                }
            }
            for i, kid in enumerate(ordered)
        ]
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

GRADE_LABELS = {1: "G1", 2: "G2", 3: "G3", 4: "G4", 5: "G5", 6: "G6",
                8: "G8 (jouyou)", 9: "G9 (jinmeiyou)", 10: "G10 (jinmeiyou-var)"}

def main():
    parser = argparse.ArgumentParser(description="Generate kanji learning order document")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without writing files")
    args = parser.parse_args()

    print("Generating Kanji Learning Order")
    print("=" * 40)

    # Step 1: Load kanji documents
    print("\n1. Loading kanji documents...")
    kanji = load_kanji_documents()
    print(f"   Loaded {len(kanji)} kanji")

    # Step 2: Load kanji-to-kanji dependencies
    print("\n2. Loading kanji dependencies...")
    kanji_deps = load_kanji_dependencies()
    total_edges = sum(len(v) for v in kanji_deps.values())
    print(f"   Loaded {len(kanji_deps)} dependency documents ({total_edges} edges)")

    # Step 3: Load grapheme readiness data
    print("\n3. Loading grapheme readiness data...")
    grapheme_positions = load_grapheme_learning_order()
    if grapheme_positions:
        print(f"   Grapheme learning order: {len(grapheme_positions)} positions")
    else:
        print("   No grapheme learning order — readiness will be default for all")

    kanji_grapheme_deps = load_kanji_grapheme_dependencies()
    print(f"   Kanji-grapheme dependencies: {len(kanji_grapheme_deps)} kanji")

    readiness = compute_grapheme_readiness(kanji_grapheme_deps, grapheme_positions)
    kanji_with_readiness = sum(1 for v in readiness.values() if v >= 0)
    print(f"   Kanji with readiness scores: {kanji_with_readiness}")

    # Step 4: Load kanjidic grades
    print("\n4. Loading kanjidic grades...")
    grades = load_kanjidic_grades()
    matched = sum(1 for kid in kanji if kid in grades)
    print(f"   Matched grades for {matched}/{len(kanji)} kanji")

    # Show grade distribution
    grade_dist: dict[int, int] = {}
    for kid in kanji:
        g = grades.get(kid, DEFAULT_GRADE)
        grade_dist[g] = grade_dist.get(g, 0) + 1
    for g in sorted(grade_dist.keys()):
        label = GRADE_LABELS.get(g, f"G{g}" if g != DEFAULT_GRADE else "no grade")
        print(f"     {label}: {grade_dist[g]}")

    # Step 5: Load popularity
    print("\n5. Loading popularity data...")
    popularity = load_popularity()
    matched_pop = sum(1 for kid in kanji if popularity.get(kid, 0) > 0)
    print(f"   Kanji with popularity > 0: {matched_pop}/{len(kanji)}")

    # Step 6: Compute order
    print("\n6. Computing order...")
    ordered = compute_order(kanji, readiness, grades, popularity)
    print(f"   Ordered {len(ordered)} kanji")

    # Show first/last entries
    print(f"\n   First 15:")
    for i, kid in enumerate(ordered[:15]):
        doc = kanji.get(kid, {})
        g = grades.get(kid, DEFAULT_GRADE)
        r = readiness.get(kid, -1)
        p = popularity.get(kid, 0)
        label = GRADE_LABELS.get(g, f"G{g}" if g != DEFAULT_GRADE else "—")
        print(f"     {i:4d}. {doc.get('symbol', '?')}  "
              f"strokes={doc.get('strokeCount', '?'):>2}  "
              f"ready={r:>3}  grade={label:<18s}  pop={p}")

    print(f"\n   Last 10:")
    for i, kid in enumerate(ordered[-10:], len(ordered) - 10):
        doc = kanji.get(kid, {})
        g = grades.get(kid, DEFAULT_GRADE)
        r = readiness.get(kid, -1)
        p = popularity.get(kid, 0)
        label = GRADE_LABELS.get(g, f"G{g}" if g != DEFAULT_GRADE else "—")
        print(f"     {i:4d}. {doc.get('symbol', '?')}  "
              f"strokes={doc.get('strokeCount', '?'):>2}  "
              f"ready={r:>3}  grade={label:<18s}  pop={p}")

    # Step 7: Validate dependency ordering
    print("\n7. Validating dependency ordering...")
    violations = validate_order(ordered, kanji_deps, kanji)
    if violations:
        print(f"   WARNINGS: {len(violations)} dependency violation(s)")
        # Show first 20 violations
        for v in violations[:20]:
            print(v)
        if len(violations) > 20:
            print(f"   ... and {len(violations) - 20} more")
    else:
        print("   All dependencies satisfied.")

    # Step 8: Generate document
    print("\n8. Generating learning order document...")
    doc = create_learning_order_document(ordered)

    filename = "japanese-kanji-learning-order-default.json"
    filepath = LEARNING_ORDER_DOCS / filename

    if args.dry_run:
        print(f"   DRY RUN — would write {filepath}")
    else:
        LEARNING_ORDER_DOCS.mkdir(parents=True, exist_ok=True)
        if write_json_document(doc, filepath):
            print(f"   Written: {filepath.name}")
        else:
            print(f"   Unchanged: {filepath.name}")

    # Summary
    print("\n" + "=" * 40)
    print("Summary:")
    print(f"  Total kanji ordered: {len(ordered)}")
    print(f"  Stroke count range: "
          f"{kanji[ordered[0]].get('strokeCount', '?')}-"
          f"{kanji[ordered[-1]].get('strokeCount', '?')}")
    print(f"  Dependency violations: {len(violations)}")

    print("\nDone.")


if __name__ == "__main__":
    main()
