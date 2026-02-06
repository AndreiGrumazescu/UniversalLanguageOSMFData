#!/usr/bin/env python3
"""
kanji_generator.py

Generate OSMF kanji documents from kanjidic2.xml.

Filters to Jouyou and Jinmeiyou kanji (entries with a grade level in kanjidic2)
and produces one document per kanji in data/kanji/documents/.

Usage:
    python generators/kanji_generator.py [--dry-run]
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.kanjidic import KanjiEntry, parse_kanjidic_full
from lib.normalizers import nfkc_plus
from lib.paths import KANJI_DOCS
from lib.grapheme_io import write_json_document, delete_json_document


def codepoint_str(char: str) -> str:
    """Convert a character to 'U+XXXX' format."""
    cp = ord(char)
    if cp > 0xFFFF:
        return f"U+{cp:05X}"
    return f"U+{cp:04X}"


def build_kanji_document(entry: KanjiEntry) -> dict:
    """
    Build an OSMF kanji document from a KanjiEntry.

    Normalizes the literal (via nfkc_plus) before computing the unicode
    codepoint, so CJK Compatibility Ideographs map to their base forms.

    Args:
        entry: Parsed kanji entry from kanjidic2

    Returns:
        Document dict matching japanese-kanji.schema.json
    """
    normalized = nfkc_plus(entry.literal)
    unicode = codepoint_str(normalized)

    doc = {
        "$id": f"kanji:{unicode}",
        "unicode": unicode,
        "symbol": normalized,
        "meanings": entry.meanings,
    }

    if entry.onyomi:
        doc["onyomi"] = entry.onyomi

    if entry.kunyomi:
        doc["kunyomi"] = entry.kunyomi

    if entry.stroke_count is not None:
        doc["strokeCount"] = entry.stroke_count

    doc["jlptLevel"] = "unspecified"

    return doc


def doc_filename(doc: dict) -> str:
    """Get the filename for a kanji document."""
    return f"{doc['$id']}.json"


def main():
    parser = argparse.ArgumentParser(description="Generate kanji documents from kanjidic2")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without writing files")
    args = parser.parse_args()

    print("Generating Kanji Documents")
    print("=" * 40)

    # Step 1: Parse kanjidic2
    print("\n1. Parsing kanjidic2.xml...")
    all_entries = parse_kanjidic_full()
    print(f"   Total entries in kanjidic2: {len(all_entries)}")

    # Step 2: Filter to graded kanji (Jouyou + Jinmeiyou)
    graded = [e for e in all_entries if e.grade is not None]
    print(f"   Graded (Jouyou + Jinmeiyou): {len(graded)}")

    # Step 3: Build documents
    print("\n2. Building documents...")
    new_documents: dict[str, dict] = {}  # filename -> document

    skipped_no_meanings = 0
    skipped_normalized_dupes = 0
    for entry in graded:
        if not entry.meanings:
            skipped_no_meanings += 1
            continue

        doc = build_kanji_document(entry)
        filename = doc_filename(doc)

        # After normalization, multiple kanjidic2 entries can map to the same
        # character (e.g. CJK Compatibility Ideograph + base form).
        # Keep the first (base-form) entry since kanjidic2 lists them first.
        if filename in new_documents:
            skipped_normalized_dupes += 1
            continue

        new_documents[filename] = doc

    print(f"   Documents to generate: {len(new_documents)}")
    if skipped_no_meanings:
        print(f"   Skipped (no English meanings): {skipped_no_meanings}")
    if skipped_normalized_dupes:
        print(f"   Skipped (normalized duplicates): {skipped_normalized_dupes}")

    # Step 4: Compare with existing documents
    print("\n3. Comparing with existing documents...")
    KANJI_DOCS.mkdir(parents=True, exist_ok=True)

    existing_files = set(f.name for f in KANJI_DOCS.glob("*.json"))
    new_files = set(new_documents.keys())

    to_create = new_files - existing_files
    to_update = new_files & existing_files
    to_delete = existing_files - new_files

    print(f"   New: {len(to_create)}")
    print(f"   Update: {len(to_update)}")
    print(f"   Delete: {len(to_delete)}")

    # Step 5: Write/delete files
    if args.dry_run:
        print("\n4. DRY RUN - no files modified")
        if to_create:
            samples = sorted(to_create)[:5]
            print(f"   Would create {len(to_create)} files (e.g., {', '.join(samples)})")
        if to_delete:
            samples = sorted(to_delete)[:5]
            print(f"   Would delete {len(to_delete)} files (e.g., {', '.join(samples)})")
    else:
        print("\n4. Writing files...")

        created = 0
        updated = 0
        for filename, doc in new_documents.items():
            filepath = KANJI_DOCS / filename
            was_new = not filepath.exists()
            if write_json_document(doc, filepath):
                if was_new:
                    created += 1
                else:
                    updated += 1

        deleted = 0
        for filename in to_delete:
            filepath = KANJI_DOCS / filename
            if delete_json_document(filepath):
                deleted += 1

        print(f"   Created: {created}")
        print(f"   Updated: {updated}")
        print(f"   Deleted: {deleted}")

    # Summary
    print("\n" + "=" * 40)
    print("Summary:")

    # Grade breakdown
    grade_counts = {}
    for entry in graded:
        if entry.meanings:
            grade_counts[entry.grade] = grade_counts.get(entry.grade, 0) + 1

    grade_labels = {
        1: "Grade 1 (kyouiku)", 2: "Grade 2 (kyouiku)", 3: "Grade 3 (kyouiku)",
        4: "Grade 4 (kyouiku)", 5: "Grade 5 (kyouiku)", 6: "Grade 6 (kyouiku)",
        8: "Grade 8 (jouyou remainder)", 9: "Jinmeiyou", 10: "Jinmeiyou variant",
    }
    for grade in sorted(grade_counts):
        label = grade_labels.get(grade, f"Grade {grade}")
        print(f"  {label}: {grade_counts[grade]}")

    print(f"  Total: {len(new_documents)}")
    print("\nDone.")


if __name__ == "__main__":
    main()
