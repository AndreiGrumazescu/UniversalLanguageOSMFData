#!/usr/bin/env python3
"""
regenerate_grapheme_dependencies.py

Regenerates grapheme-dependency documents using the CHISE IDS (primary)
and KanjiVG (fallback) decomposition algorithm.

For each grapheme, this script:
1. Finds its components using the unified algorithm
2. Filters to only components that are also graphemes (or grapheme variants)
3. Creates/updates dependency documents for graphemes with grapheme components
4. Removes stale dependency documents

Usage:
    python generators/grapheme_dependencies.py [--dry-run]
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import DEPENDENCY_DOCS
from lib.grapheme_io import (
    load_graphemes_with_mappings,
    build_variant_to_symbol_mapping,
    write_json_document,
    delete_json_document,
)
from lib.normalizers import make_grapheme_normalizer
from adapters.component_analysis import (
    load_chise_ids,
    load_kanjivg_index,
    get_all_components_expanded,
)


# ---------------------------------------------------------------------------
# Dependency Document Generation
# ---------------------------------------------------------------------------

def create_dependency_document(grapheme_id: str, component_ids: list[str]) -> dict:
    """
    Create a dependency document structure.

    Args:
        grapheme_id: The $id of the parent grapheme (e.g., "grapheme:U+4E01")
        component_ids: List of component grapheme $ids

    Returns:
        Dependency document dict
    """
    # Extract unicode from grapheme_id (e.g., "grapheme:U+4E01" -> "U+4E01")
    unicode_part = grapheme_id.replace("grapheme:", "")
    dep_id = f"grapheme-dep:{unicode_part}"

    return {
        "$id": dep_id,
        "connectors": {
            "parent": {
                "$id": grapheme_id
            }
        },
        "many": [
            {
                "connectors": {
                    "component": {
                        "$id": cid
                    }
                }
            }
            for cid in component_ids
        ]
    }


def get_dependency_filename(grapheme_id: str) -> str:
    """Get the filename for a dependency document."""
    unicode_part = grapheme_id.replace("grapheme:", "")
    return f"grapheme-dep:{unicode_part}.json"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Regenerate grapheme dependency documents")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without writing files")
    args = parser.parse_args()

    print("Regenerating Grapheme Dependencies")
    print("=" * 40)
    print("Using CHISE IDS (primary) + KanjiVG (fallback)")

    # Step 1: Load graphemes
    print("\n1. Loading graphemes...")
    graphemes, symbol_to_id, variant_to_id = load_graphemes_with_mappings()
    print(f"   Loaded {len(graphemes)} graphemes")
    print(f"   Found {len(variant_to_id)} variants")

    # Step 2: Load decomposition data
    print("\n2. Loading decomposition data...")
    chise_ids = load_chise_ids()
    print(f"   CHISE IDS: {len(chise_ids)} characters")
    kanjivg_chars = load_kanjivg_index()
    print(f"   KanjiVG: {len(kanjivg_chars)} characters")

    # Step 3: Create normalizer
    variant_to_symbol = build_variant_to_symbol_mapping(graphemes, symbol_to_id, variant_to_id)
    normalizer = make_grapheme_normalizer(variant_to_symbol)

    # Build id_to_doc mapping for quick lookup
    id_to_doc: dict[str, dict] = graphemes

    # Step 4: Process each grapheme with expanded search
    print("\n3. Processing graphemes (expanded search)...")
    new_dependencies: dict[str, dict] = {}  # grapheme_id -> dependency document
    stats = {"with_deps": 0, "without_deps": 0}

    for gid, doc in graphemes.items():
        symbol = doc.get("symbol")
        if not symbol:
            continue

        # Get ALL components using expanded search (union of CHISE + KanjiVG, original + normalized)
        giant_set = get_all_components_expanded(symbol, chise_ids, kanjivg_chars, normalizer)

        # Also search children of this grapheme's variants
        for variant in doc.get("variants", []):
            variant_symbol = variant.get("symbol")
            if variant_symbol:
                variant_children = get_all_components_expanded(variant_symbol, chise_ids, kanjivg_chars, normalizer)
                giant_set.update(variant_children)

        if not giant_set:
            stats["without_deps"] += 1
            continue

        # For each component in giant_set that is a grapheme, also get children of ITS variants
        expanded_giant_set = set(giant_set)  # Copy to avoid modifying during iteration
        for comp in giant_set:
            normalized_comp = normalizer(comp)
            # Check if component is a grapheme
            comp_gid = symbol_to_id.get(normalized_comp) or variant_to_id.get(normalized_comp)
            if comp_gid and comp_gid in id_to_doc:
                comp_doc = id_to_doc[comp_gid]
                # Get children of the component's variants
                for variant in comp_doc.get("variants", []):
                    variant_symbol = variant.get("symbol")
                    if variant_symbol:
                        variant_children = get_all_components_expanded(variant_symbol, chise_ids, kanjivg_chars, normalizer)
                        expanded_giant_set.update(variant_children)

        giant_set = expanded_giant_set

        # Normalize all children and build dict: normalized -> [originals]
        # Then filter to only those that are graphemes
        normalized_to_originals: dict[str, list[str]] = {}
        for comp in giant_set:
            normalized_comp = normalizer(comp)
            if normalized_comp not in normalized_to_originals:
                normalized_to_originals[normalized_comp] = []
            if comp not in normalized_to_originals[normalized_comp]:
                normalized_to_originals[normalized_comp].append(comp)

        # Filter to only normalized components that are graphemes
        grapheme_component_ids: list[str] = []
        for normalized_comp in normalized_to_originals.keys():
            # Check if it's a grapheme (primary or variant)
            comp_gid = symbol_to_id.get(normalized_comp)
            if not comp_gid:
                comp_gid = variant_to_id.get(normalized_comp)

            if comp_gid and comp_gid != gid:  # Don't include self
                if comp_gid not in grapheme_component_ids:  # Deduplicate
                    grapheme_component_ids.append(comp_gid)

        if grapheme_component_ids:
            dep_doc = create_dependency_document(gid, grapheme_component_ids)
            new_dependencies[gid] = dep_doc
            stats["with_deps"] += 1
        else:
            stats["without_deps"] += 1

    print(f"   Graphemes with grapheme-components: {stats['with_deps']}")
    print(f"   Graphemes without grapheme-components: {stats['without_deps']}")

    # Step 5: Compare with existing dependencies
    print("\n4. Comparing with existing dependencies...")
    DEPENDENCY_DOCS.mkdir(parents=True, exist_ok=True)

    existing_files = set(f.name for f in DEPENDENCY_DOCS.glob("*.json"))
    new_files = set(get_dependency_filename(gid) for gid in new_dependencies.keys())

    to_create = new_files - existing_files
    to_update = new_files & existing_files
    to_delete = existing_files - new_files

    print(f"   New: {len(to_create)}")
    print(f"   Update: {len(to_update)}")
    print(f"   Delete: {len(to_delete)}")

    # Step 6: Write/delete files
    if args.dry_run:
        print("\n5. DRY RUN - no files modified")
        if to_create:
            print(f"   Would create: {sorted(to_create)[:5]}{'...' if len(to_create) > 5 else ''}")
        if to_delete:
            print(f"   Would delete: {sorted(to_delete)[:5]}{'...' if len(to_delete) > 5 else ''}")
    else:
        print("\n5. Writing files...")

        # Create/update
        created = 0
        updated = 0
        for gid, dep_doc in new_dependencies.items():
            filename = get_dependency_filename(gid)
            filepath = DEPENDENCY_DOCS / filename

            was_new = not filepath.exists()
            if write_json_document(dep_doc, filepath):
                if was_new:
                    created += 1
                else:
                    updated += 1

        # Delete stale
        deleted = 0
        for filename in to_delete:
            filepath = DEPENDENCY_DOCS / filename
            if delete_json_document(filepath):
                deleted += 1

        print(f"   Created: {created}")
        print(f"   Updated: {updated}")
        print(f"   Deleted: {deleted}")

    # Summary
    print("\n" + "=" * 40)
    print("Summary:")
    print(f"  Total graphemes: {len(graphemes)}")
    print(f"  Graphemes with dependencies: {len(new_dependencies)}")
    print(f"  Total component relationships: {sum(len(d['many']) for d in new_dependencies.values())}")

    print("\nDone.")


if __name__ == "__main__":
    main()
