#!/usr/bin/env python3
"""
kanji_grapheme_dependency_generator.py

Generate kanji-grapheme-dependency relational documents.

For each kanji, decomposes it into components using CHISE IDS (primary)
and KanjiVG (fallback), and stores any component that is also a grapheme
as a relationship. Iterates on un-normalized kanji from kanjidic2 for
better decomposition coverage, but stores normalized IDs in the output
documents.

Usage:
    python generators/kanji_grapheme_dependency_generator.py [--dry-run]
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.kanjidic import parse_kanjidic_full
from adapters.component_analysis import (
    load_chise_ids,
    load_kanjivg_index,
    get_all_components_expanded,
)
from lib.normalizers import nfkc_plus
from lib.paths import KANJI_GRAPHEME_DEP_DOCS
from lib.grapheme_io import (
    load_graphemes_with_mappings,
    write_json_document,
    delete_json_document,
)


def codepoint_str(char: str) -> str:
    """Convert a character to 'U+XXXX' format."""
    cp = ord(char)
    if cp > 0xFFFF:
        return f"U+{cp:05X}"
    return f"U+{cp:04X}"


# ---------------------------------------------------------------------------
# Document Generation
# ---------------------------------------------------------------------------

def create_grapheme_dep_document(kanji_id: str, grapheme_ids: list[str]) -> dict:
    """
    Create a kanji-grapheme dependency document.

    Args:
        kanji_id: The $id of the parent kanji (e.g., "kanji:U+660E")
        grapheme_ids: List of grapheme $ids (e.g., ["U+65E5", "U+6708"])

    Returns:
        Dependency document dict
    """
    unicode_part = kanji_id.replace("kanji:", "")
    dep_id = f"kanji-grapheme-dep:{unicode_part}"

    return {
        "$id": dep_id,
        "connectors": {
            "parent": {
                "$id": kanji_id
            }
        },
        "many": [
            {
                "connectors": {
                    "component": {
                        "$id": gid
                    }
                }
            }
            for gid in grapheme_ids
        ]
    }


def get_dep_filename(kanji_id: str) -> str:
    """Get the filename for a kanji-grapheme dependency document."""
    unicode_part = kanji_id.replace("kanji:", "")
    return f"kanji-grapheme-dep:{unicode_part}.json"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate kanji-grapheme dependency documents")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without writing files")
    args = parser.parse_args()

    print("Generating Kanji-Grapheme Dependencies")
    print("=" * 40)
    print("Using CHISE IDS (primary) + KanjiVG (fallback)")

    # Step 1: Parse kanjidic2 and build kanji symbol set
    print("\n1. Parsing kanjidic2.xml...")
    all_entries = parse_kanjidic_full()
    graded = [e for e in all_entries if e.grade is not None and e.meanings]
    print(f"   Total entries: {len(all_entries)}")
    print(f"   Graded with meanings: {len(graded)}")

    # Build normalized kanji set (same dedup logic as other generators)
    kanji_entries: list[tuple[str, object]] = []
    seen_normalized: set[str] = set()

    for entry in graded:
        normalized = nfkc_plus(entry.literal)
        if normalized in seen_normalized:
            continue
        seen_normalized.add(normalized)

        unicode = codepoint_str(normalized)
        kanji_id = f"kanji:{unicode}"
        kanji_entries.append((kanji_id, entry))

    print(f"   Unique kanji: {len(kanji_entries)}")

    # Step 2: Load grapheme set
    print("\n2. Loading grapheme documents...")
    graphemes, symbol_to_id, variant_to_id = load_graphemes_with_mappings()
    print(f"   Graphemes: {len(graphemes)}")
    print(f"   Primary symbols: {len(symbol_to_id)}")
    print(f"   Variant symbols: {len(variant_to_id)}")

    # Step 3: Load decomposition data
    print("\n3. Loading decomposition data...")
    chise_ids = load_chise_ids()
    print(f"   CHISE IDS: {len(chise_ids)} characters")
    kanjivg_chars = load_kanjivg_index()
    print(f"   KanjiVG: {len(kanjivg_chars)} characters")

    # Step 4: Process each kanji
    print("\n4. Processing kanji...")
    new_dependencies: dict[str, dict] = {}

    for kanji_id, entry in kanji_entries:
        # Use UN-normalized literal for decomposition (better coverage in
        # CHISE/KanjiVG). get_all_components_expanded also tries the
        # nfkc_plus-normalized form internally.
        components = get_all_components_expanded(
            entry.literal, chise_ids, kanjivg_chars, nfkc_plus
        )

        # Filter to components that are graphemes in our set
        grapheme_ids: list[str] = []
        for comp in components:
            normalized_comp = nfkc_plus(comp)

            # Check primary grapheme symbols
            gid = symbol_to_id.get(normalized_comp)
            # Fall back to variant symbols (maps to canonical grapheme ID)
            if not gid:
                gid = variant_to_id.get(normalized_comp)

            if gid and gid not in grapheme_ids:
                grapheme_ids.append(gid)

        if grapheme_ids:
            dep_doc = create_grapheme_dep_document(kanji_id, grapheme_ids)
            new_dependencies[kanji_id] = dep_doc

    with_deps = len(new_dependencies)
    without_deps = len(kanji_entries) - with_deps
    print(f"   Kanji with grapheme components: {with_deps}")
    print(f"   Kanji without grapheme components: {without_deps}")

    # Step 5: Compare with existing documents
    print("\n5. Comparing with existing documents...")
    KANJI_GRAPHEME_DEP_DOCS.mkdir(parents=True, exist_ok=True)

    existing_files = set(f.name for f in KANJI_GRAPHEME_DEP_DOCS.glob("*.json"))
    new_files = set(get_dep_filename(kid) for kid in new_dependencies.keys())

    to_create = new_files - existing_files
    to_update = new_files & existing_files
    to_delete = existing_files - new_files

    print(f"   New: {len(to_create)}")
    print(f"   Update: {len(to_update)}")
    print(f"   Delete: {len(to_delete)}")

    # Step 6: Write/delete files
    if args.dry_run:
        print("\n6. DRY RUN - no files modified")
        if to_create:
            samples = sorted(to_create)[:5]
            print(f"   Would create {len(to_create)} files (e.g., {', '.join(samples)})")
        if to_delete:
            samples = sorted(to_delete)[:5]
            print(f"   Would delete {len(to_delete)} files (e.g., {', '.join(samples)})")
    else:
        print("\n6. Writing files...")

        created = 0
        updated = 0
        for kanji_id, dep_doc in new_dependencies.items():
            filename = get_dep_filename(kanji_id)
            filepath = KANJI_GRAPHEME_DEP_DOCS / filename
            was_new = not filepath.exists()
            if write_json_document(dep_doc, filepath):
                if was_new:
                    created += 1
                else:
                    updated += 1

        deleted = 0
        for filename in to_delete:
            filepath = KANJI_GRAPHEME_DEP_DOCS / filename
            if delete_json_document(filepath):
                deleted += 1

        print(f"   Created: {created}")
        print(f"   Updated: {updated}")
        print(f"   Deleted: {deleted}")

    # Summary
    print("\n" + "=" * 40)
    print("Summary:")
    print(f"  Total kanji: {len(kanji_entries)}")
    print(f"  Kanji with grapheme components: {len(new_dependencies)}")
    print(f"  Total grapheme relationships: {sum(len(d['many']) for d in new_dependencies.values())}")
    print("\nDone.")


if __name__ == "__main__":
    main()
