#!/usr/bin/env python3
"""
regenerate_grapheme_variant_groups.py

Regenerates grapheme-variant-group documents based on grapheme naming conventions.

Grouping logic:
- If a grapheme has "Variant" in its name, find the base grapheme(s) with the
  matching base name (name without " Variant")
- If no exact match, try partial match on the first word of the base name
- All matching graphemes are grouped together

Example:
- "Water" and "Water Variant" form a group named "Water"
- "Person", "Person Side Variant", "Person Top Variant" form a group named "Person"

Usage:
    python generators/grapheme_variant_groups.py [--dry-run]
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import VARIANT_GROUP_DOCS
from lib.grapheme_io import load_graphemes, write_json_document, delete_json_document


# ---------------------------------------------------------------------------
# Variant Group Detection
# ---------------------------------------------------------------------------

def find_variant_groups(graphemes: dict[str, dict]) -> dict[str, set[str]]:
    """
    Find variant groups based on naming conventions.

    Returns:
        Dict mapping group_name -> set of grapheme $ids
    """
    groups: dict[str, set[str]] = {}

    for gid, doc in graphemes.items():
        name = doc.get("name", "")

        if "Variant" not in name:
            continue

        # Extract base name (remove " Variant" suffix, and any positional word like "Side", "Top")
        base_name = name.replace(" Variant", "").strip()

        # Try exact base name match first
        matches = [
            (g, d) for g, d in graphemes.items()
            if g != gid and (
                d.get("name") == base_name or
                base_name in d.get("nameAliases", [])
            )
        ]

        if matches:
            # Use the base grapheme's name as group name
            group_name = matches[0][1].get("name")
            if group_name not in groups:
                groups[group_name] = set()
            groups[group_name].add(gid)
            for match_id, _ in matches:
                groups[group_name].add(match_id)
        else:
            # Try partial match - first word of base_name
            first_word = base_name.split()[0] if base_name else ""
            partial_matches = [
                (g, d) for g, d in graphemes.items()
                if g != gid and d.get("name") == first_word
            ]

            if partial_matches:
                group_name = partial_matches[0][1].get("name")
                if group_name not in groups:
                    groups[group_name] = set()
                groups[group_name].add(gid)
                for match_id, _ in partial_matches:
                    groups[group_name].add(match_id)
            else:
                print(f"  WARNING: No match found for '{name}' (base='{base_name}')")

    return groups


# ---------------------------------------------------------------------------
# Document Generation
# ---------------------------------------------------------------------------

def create_variant_group_document(group_name: str, member_ids: list[str]) -> dict:
    """
    Create a variant group document structure.

    Args:
        group_name: The semantic name of the group (e.g., "Water")
        member_ids: List of grapheme $ids in this group

    Returns:
        Variant group document dict
    """
    # Create document ID based on group name (lowercase, hyphenated)
    doc_id = f"grapheme-variant-group:{group_name.lower().replace(' ', '-')}"

    return {
        "$id": doc_id,
        "name": group_name,
        "many": [
            {
                "connectors": {
                    "member": {
                        "$id": member_id
                    }
                }
            }
            for member_id in sorted(member_ids)
        ]
    }


def get_group_filename(group_name: str) -> str:
    """Get the filename for a variant group document."""
    doc_id = f"grapheme-variant-group:{group_name.lower().replace(' ', '-')}"
    return f"{doc_id}.json"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Regenerate grapheme variant group documents")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without writing files")
    args = parser.parse_args()

    print("Regenerating Grapheme Variant Groups")
    print("=" * 40)

    # Step 1: Load graphemes
    print("\n1. Loading graphemes...")
    graphemes = load_graphemes()
    print(f"   Loaded {len(graphemes)} graphemes")

    # Step 2: Find variant groups
    print("\n2. Finding variant groups...")
    groups = find_variant_groups(graphemes)
    print(f"   Found {len(groups)} variant groups")

    # Show groups
    for group_name in sorted(groups.keys()):
        member_ids = groups[group_name]
        members_str = ", ".join(
            graphemes[gid].get("symbol", "?") for gid in sorted(member_ids)
        )
        print(f"   {group_name}: {members_str}")

    # Step 3: Generate documents
    print("\n3. Generating documents...")
    new_documents: dict[str, dict] = {}  # filename -> document

    for group_name, member_ids in groups.items():
        doc = create_variant_group_document(group_name, list(member_ids))
        filename = get_group_filename(group_name)
        new_documents[filename] = doc

    # Step 4: Compare with existing documents
    print("\n4. Comparing with existing documents...")
    VARIANT_GROUP_DOCS.mkdir(parents=True, exist_ok=True)

    existing_files = set(f.name for f in VARIANT_GROUP_DOCS.glob("*.json"))
    new_files = set(new_documents.keys())

    to_create = new_files - existing_files
    to_update = new_files & existing_files
    to_delete = existing_files - new_files

    print(f"   New: {len(to_create)}")
    print(f"   Update: {len(to_update)}")
    print(f"   Delete: {len(to_delete)}")

    # Step 5: Write/delete files
    if args.dry_run:
        print("\n5. DRY RUN - no files modified")
        if to_create:
            print(f"   Would create: {sorted(to_create)}")
        if to_delete:
            print(f"   Would delete: {sorted(to_delete)}")
    else:
        print("\n5. Writing files...")

        # Create/update
        created = 0
        updated = 0
        for filename, doc in new_documents.items():
            filepath = VARIANT_GROUP_DOCS / filename

            was_new = not filepath.exists()
            if write_json_document(doc, filepath):
                if was_new:
                    created += 1
                else:
                    updated += 1

        # Delete stale
        deleted = 0
        for filename in to_delete:
            filepath = VARIANT_GROUP_DOCS / filename
            if delete_json_document(filepath):
                deleted += 1

        print(f"   Created: {created}")
        print(f"   Updated: {updated}")
        print(f"   Deleted: {deleted}")

    # Summary
    print("\n" + "=" * 40)
    print("Summary:")
    print(f"  Total variant groups: {len(groups)}")
    print(f"  Total graphemes in groups: {sum(len(m) for m in groups.values())}")

    print("\nDone.")


if __name__ == "__main__":
    main()
