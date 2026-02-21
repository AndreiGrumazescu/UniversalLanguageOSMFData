#!/usr/bin/env python3
"""
learning_order_generator.py

Generates a learning-order document for Japanese graphemes.

Ordering criteria:
1. Variant groups are kept together — the base (non-variant) grapheme determines
   group position, and all variants follow immediately after the base.
2. Primary sort: stroke count ascending (of the base grapheme for groups)
3. Secondary sort: popularity descending (of the base grapheme for groups)
4. Tertiary sort: $id ascending (deterministic tiebreaker)

Validates that the stroke-count ordering satisfies all dependency constraints
(every component appears before its parent in the final order).

Usage:
    python generators/learning_order_generator.py [--dry-run]
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import LEARNING_ORDER_DOCS, POPULARITY_JSON
from lib.grapheme_io import (
    load_graphemes,
    load_dependencies,
    load_variant_groups,
    write_json_document,
)


# ---------------------------------------------------------------------------
# Popularity Loading
# ---------------------------------------------------------------------------

def load_popularity(json_path: Path = POPULARITY_JSON) -> dict[str, int]:
    """
    Load per-grapheme popularity from the component-popularity.json report.

    Returns:
        Dict mapping grapheme $id -> popularity count
    """
    if not json_path.exists():
        print(f"  WARNING: {json_path} not found. Run find_component_popularity.py first.")
        print("  Falling back to popularity=0 for all graphemes.")
        return {}

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    popularity: dict[str, int] = {}
    for stroke_group in data.get("by_stroke_count", {}).values():
        for entry in stroke_group:
            gid = entry.get("grapheme_id")
            if gid and entry.get("is_grapheme"):
                popularity[gid] = entry.get("popularity", 0)

    return popularity


# ---------------------------------------------------------------------------
# Variant Group Mapping
# ---------------------------------------------------------------------------

def build_variant_group_map(
    variant_groups: dict[str, dict],
    graphemes: dict[str, dict],
) -> tuple[dict[str, str], dict[str, list[str]]]:
    """
    Build mappings between graphemes and their variant groups.

    Returns:
        Tuple of:
        - member_to_group: maps grapheme $id -> group $id (for grouped graphemes)
        - group_members: maps group $id -> ordered list of member $ids
          (base grapheme first, then variants sorted by $id)
    """
    member_to_group: dict[str, str] = {}
    group_members: dict[str, list[str]] = {}

    for group_id, group_doc in variant_groups.items():
        members = []
        for item in group_doc.get("many", []):
            mid = item["connectors"]["member"]["$id"]
            members.append(mid)
            member_to_group[mid] = group_id

        # Identify the base grapheme: the one whose name does NOT contain "Variant"
        base_ids = []
        variant_ids = []
        for mid in members:
            doc = graphemes.get(mid, {})
            name = doc.get("name", "")
            if "Variant" in name:
                variant_ids.append(mid)
            else:
                base_ids.append(mid)

        # Base first, then variants (each sub-list sorted by $id for determinism)
        ordered = sorted(base_ids) + sorted(variant_ids)
        group_members[group_id] = ordered

    return member_to_group, group_members


# ---------------------------------------------------------------------------
# Ordering
# ---------------------------------------------------------------------------

def compute_order(
    graphemes: dict[str, dict],
    popularity: dict[str, int],
    member_to_group: dict[str, str],
    group_members: dict[str, list[str]],
) -> list[str]:
    """
    Compute the final ordered list of grapheme $ids.

    Graphemes in variant groups are represented by their base grapheme for
    sorting purposes; the full group is emitted together at that position.

    Sort key: (strokeCount ASC, popularity DESC, $id ASC)

    Returns:
        Ordered list of grapheme $ids
    """
    # Determine which graphemes are "sort representatives"
    # - Ungrouped graphemes represent themselves
    # - For variant groups, only the base (first member) represents the group
    already_grouped: set[str] = set()
    sort_entries: list[tuple[tuple[int, int, str], list[str]]] = []

    for gid, doc in graphemes.items():
        if gid in already_grouped:
            continue

        if gid in member_to_group:
            group_id = member_to_group[gid]
            members = group_members[group_id]

            # Skip if we already processed this group via another member
            if any(m in already_grouped for m in members):
                continue

            for m in members:
                already_grouped.add(m)

            # Use the base (first) member for sort key
            base_id = members[0]
            base_doc = graphemes.get(base_id, {})
            stroke_count = base_doc.get("strokeCount", 999)
            pop = popularity.get(base_id, 0)

            sort_key = (stroke_count, -pop, base_id)
            sort_entries.append((sort_key, members))
        else:
            stroke_count = doc.get("strokeCount", 999)
            pop = popularity.get(gid, 0)

            sort_key = (stroke_count, -pop, gid)
            sort_entries.append((sort_key, [gid]))

    sort_entries.sort(key=lambda x: x[0])

    # Flatten to ordered list
    ordered: list[str] = []
    for _, ids in sort_entries:
        ordered.extend(ids)

    return ordered


# ---------------------------------------------------------------------------
# Dependency Validation
# ---------------------------------------------------------------------------

def validate_order(
    ordered: list[str],
    deps: dict[str, list[str]],
    graphemes: dict[str, dict],
) -> list[str]:
    """
    Validate that the ordering satisfies all dependency constraints:
    every component must appear before its parent.

    Returns:
        List of violation descriptions (empty if valid)
    """
    position: dict[str, int] = {gid: i for i, gid in enumerate(ordered)}
    violations: list[str] = []

    for parent_id, component_ids in deps.items():
        parent_pos = position.get(parent_id)
        if parent_pos is None:
            continue  # parent not in grapheme set

        parent_doc = graphemes.get(parent_id, {})
        parent_symbol = parent_doc.get("symbol", "?")

        for comp_id in component_ids:
            comp_pos = position.get(comp_id)
            if comp_pos is None:
                continue  # component not in grapheme set

            if comp_pos >= parent_pos:
                comp_doc = graphemes.get(comp_id, {})
                comp_symbol = comp_doc.get("symbol", "?")
                violations.append(
                    f"  {comp_symbol} ({comp_id}) at position {comp_pos} "
                    f"should come before {parent_symbol} ({parent_id}) at position {parent_pos}"
                )

    return violations


# ---------------------------------------------------------------------------
# Document Generation
# ---------------------------------------------------------------------------

def create_learning_order_document(ordered: list[str]) -> dict:
    """
    Create a learning-order OSMF document.

    Args:
        ordered: Ordered list of grapheme $ids

    Returns:
        Learning order document dict
    """
    return {
        "$schema": "../../../../shared-models/learning-order.schema.json",
        "$id": "japanese-grapheme-learning-order-default",
        "connectors": {
            "item": {}
        },
        "data": {
            "contentType": "grapheme",
            "trackId": "default",
            "trackName": "Default Grapheme Order",
            "source": "Generated: stroke count ASC, popularity DESC, $id ASC. Variant groups kept together (base first)."
        },
        "many": [
            {
                "connectors": {
                    "item": {
                        "$id": gid
                    }
                },
                "data": {
                    "position": i
                }
            }
            for i, gid in enumerate(ordered)
        ]
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate grapheme learning order document")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without writing files")
    args = parser.parse_args()

    print("Generating Grapheme Learning Order")
    print("=" * 40)

    # Step 1: Load graphemes
    print("\n1. Loading graphemes...")
    graphemes = load_graphemes()
    print(f"   Loaded {len(graphemes)} graphemes")

    # Step 2: Load dependencies
    print("\n2. Loading dependencies...")
    deps, reverse_deps = load_dependencies()
    print(f"   Loaded {len(deps)} dependency documents")

    # Step 3: Load variant groups
    print("\n3. Loading variant groups...")
    variant_groups = load_variant_groups()
    print(f"   Loaded {len(variant_groups)} variant groups")

    member_to_group, group_members = build_variant_group_map(variant_groups, graphemes)
    grouped_count = len(member_to_group)
    print(f"   {grouped_count} graphemes in variant groups")

    # Step 4: Load popularity
    print("\n4. Loading popularity data...")
    popularity = load_popularity()
    if popularity:
        print(f"   Loaded popularity for {len(popularity)} graphemes")
    else:
        print("   No popularity data — using 0 for all")

    # Step 5: Compute order
    print("\n5. Computing order...")
    ordered = compute_order(graphemes, popularity, member_to_group, group_members)
    print(f"   Ordered {len(ordered)} graphemes")

    # Show first/last few
    print(f"\n   First 10:")
    for i, gid in enumerate(ordered[:10]):
        doc = graphemes.get(gid, {})
        pop = popularity.get(gid, 0)
        print(f"     {i:3d}. {doc.get('symbol', '?')}  {doc.get('name', '?'):<25s} "
              f"strokes={doc.get('strokeCount', '?')}  pop={pop}")

    print(f"\n   Last 10:")
    for i, gid in enumerate(ordered[-10:], len(ordered) - 10):
        doc = graphemes.get(gid, {})
        pop = popularity.get(gid, 0)
        print(f"     {i:3d}. {doc.get('symbol', '?')}  {doc.get('name', '?'):<25s} "
              f"strokes={doc.get('strokeCount', '?')}  pop={pop}")

    # Step 6: Validate dependency ordering
    print("\n6. Validating dependency ordering...")
    violations = validate_order(ordered, deps, graphemes)
    if violations:
        print(f"   WARNINGS: {len(violations)} dependency violation(s):")
        for v in violations:
            print(v)
    else:
        print("   All dependencies satisfied.")

    # Step 7: Generate document
    print("\n7. Generating learning order document...")
    doc = create_learning_order_document(ordered)

    filename = "japanese-grapheme-learning-order-default.json"
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
    print(f"  Total graphemes ordered: {len(ordered)}")
    print(f"  Variant groups: {len(variant_groups)} ({grouped_count} graphemes)")
    print(f"  Dependency violations: {len(violations)}")
    print(f"  Stroke count range: "
          f"{graphemes[ordered[0]].get('strokeCount', '?')}-"
          f"{graphemes[ordered[-1]].get('strokeCount', '?')}")

    print("\nDone.")


if __name__ == "__main__":
    main()
