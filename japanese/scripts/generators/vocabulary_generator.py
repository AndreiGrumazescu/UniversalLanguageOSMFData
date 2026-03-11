#!/usr/bin/env python3
"""
vocabulary_generator.py

Generates OSMF data documents for Japanese vocabulary words.

Data sources:
- JMdict_e.xml — dictionary entries with meanings and readings
- JLPT word lists (n1.csv through n5.csv) — JLPT level grading

Only words with a JLPT level (N5–N1) are included.
Kanji characters in the written form are NFKC_PLUS normalized for compatibility
with existing kanji/grapheme documents.

Usage:
    python generators/vocabulary_generator.py [--dry-run]
"""

import argparse
import sys
import unicodedata
from pathlib import Path

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.jmdict import parse_jmdict, build_word_lookup, JMdictEntry
from adapters.jlpt import parse_jlpt_words
from lib.normalizers import nfkc_plus
from lib.paths import VOCABULARY_DOCS
from lib.grapheme_io import write_json_document, delete_json_document


# ---------------------------------------------------------------------------
# POS Tag Normalization
# ---------------------------------------------------------------------------
# JMdict entity-expanded POS tags → simplified category strings

POS_CATEGORY_MAP = {
    # Nouns
    "noun (common) (futsuumeishi)": "noun",
    "adverbial noun (fukushitekimeishi)": "noun",
    "noun, used as a suffix": "noun",
    "noun, used as a prefix": "noun",
    "noun (temporal) (jisoumeishi)": "noun",

    # Verbs
    "Ichidan verb": "ichidan verb",
    "Ichidan verb - kureru special class": "ichidan verb",
    "Godan verb with 'u' ending": "godan verb",
    "Godan verb with 'tsu' ending": "godan verb",
    "Godan verb with 'ru' ending": "godan verb",
    "Godan verb with 'ru' ending (irregular verb)": "godan verb",
    "Godan verb with 'ku' ending": "godan verb",
    "Godan verb with 'gu' ending": "godan verb",
    "Godan verb with 'bu' ending": "godan verb",
    "Godan verb with 'mu' ending": "godan verb",
    "Godan verb with 'nu' ending": "godan verb",
    "Godan verb with 'su' ending": "godan verb",
    "Kuru verb - special class": "kuru verb",
    "suru verb - included": "suru verb",
    "noun or participle which takes the aux. verb suru": "suru verb",
    "su verb - precursor to the modern suru": "suru verb",
    "suru verb - special class": "suru verb",
    "transitive verb": None,  # modifier, not a category
    "intransitive verb": None,  # modifier, not a category

    # Adjectives
    "adjective (keiyoushi)": "i-adjective",
    "adjective (keiyoushi) - yoi/ii class": "i-adjective",
    "adjectival nouns or quasi-adjectives (keiyodoshi)": "na-adjective",
    "'taru' adjective": "taru-adjective",
    "nouns which may take the genitive case particle 'no'": None,  # modifier
    "pre-noun adjectival (rentaishi)": "pre-noun adjectival",

    # Adverbs
    "adverb (fukushi)": "adverb",
    "adverb taking the 'to' particle": "adverb",

    # Others
    "conjunction": "conjunction",
    "interjection (kandoushi)": "interjection",
    "counter": "counter",
    "suffix": "suffix",
    "prefix": "prefix",
    "expressions (phrases, clauses, etc.)": "expression",
    "pronoun": "pronoun",
    "numeric": "numeric",
    "auxiliary verb": "auxiliary verb",
    "copula": "copula",
    "particle": "particle",
}


def _classify_pos(entry: JMdictEntry) -> str | None:
    """
    Determine a simplified category from the entry's POS tags.

    Iterates all POS tags in the first sense, returning the first
    non-None mapped category. Falls back to the raw first POS tag
    if nothing maps.
    """
    for sense in entry.senses:
        for pos_tag in sense.pos:
            mapped = POS_CATEGORY_MAP.get(pos_tag)
            if mapped is not None:
                return mapped
    # Fallback: use first POS tag directly if nothing mapped
    for sense in entry.senses:
        for pos_tag in sense.pos:
            if POS_CATEGORY_MAP.get(pos_tag) is not None:
                return POS_CATEGORY_MAP[pos_tag]
            # Only skip explicit None mappings (modifiers)
            if pos_tag not in POS_CATEGORY_MAP:
                return pos_tag
    return None


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def _is_kana(char: str) -> bool:
    """Check if a character is hiragana or katakana."""
    cp = ord(char)
    # Hiragana: U+3040–U+309F, Katakana: U+30A0–U+30FF
    return 0x3040 <= cp <= 0x309F or 0x30A0 <= cp <= 0x30FF


def normalize_japanese(text: str) -> str:
    """
    Apply NFKC_PLUS normalization per-character to the Japanese written form.

    Kana characters pass through unchanged. Kanji and other CJK characters
    are normalized via nfkc_plus() for compatibility with our kanji/grapheme data.
    """
    result = []
    for char in text:
        if _is_kana(char):
            result.append(char)
        else:
            result.append(nfkc_plus(char))
    return "".join(result)


def normalize_kana(text: str) -> str:
    """Apply standard NFKC normalization to kana readings."""
    return unicodedata.normalize("NFKC", text)


# ---------------------------------------------------------------------------
# Document Generation
# ---------------------------------------------------------------------------

def create_vocabulary_document(entry: JMdictEntry, jlpt_level: str) -> dict:
    """
    Create a vocabulary OSMF data document from a JMdict entry.

    First sense glosses → meanings (primary).
    Remaining senses' glosses → secondaryMeanings.
    """
    japanese = normalize_japanese(entry.japanese)
    kana = normalize_kana(entry.kana)

    # Split senses into primary and secondary
    primary_meanings: list[str] = []
    secondary_meanings: list[str] = []

    for i, sense in enumerate(entry.senses):
        if i == 0:
            primary_meanings.extend(sense.glosses)
        else:
            secondary_meanings.extend(sense.glosses)

    doc: dict = {
        "$id": f"vocab:{entry.ent_seq}",
        "japanese": japanese,
        "kana": kana,
        "meanings": primary_meanings,
        "jlptLevel": jlpt_level,
    }

    if secondary_meanings:
        doc["secondaryMeanings"] = secondary_meanings

    category = _classify_pos(entry)
    if category:
        doc["category"] = category

    return doc


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate vocabulary OSMF data documents")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without writing files")
    args = parser.parse_args()

    print("Generating Vocabulary Documents")
    print("=" * 50)

    # Step 1: Load JMdict entries
    print("\n1. Loading JMdict entries...")
    jmdict_entries = parse_jmdict()
    print(f"   Loaded {len(jmdict_entries)} JMdict entries")

    # Build lookup by (japanese, kana)
    word_lookup = build_word_lookup(jmdict_entries)
    print(f"   Built word lookup with {len(word_lookup)} (expression, reading) pairs")

    # Step 2: Load JLPT word lists
    print("\n2. Loading JLPT word lists...")
    jlpt_words = parse_jlpt_words()
    print(f"   Loaded {len(jlpt_words)} JLPT words")

    # Step 3: Match JLPT words to JMdict entries
    print("\n3. Matching JLPT words to JMdict entries...")
    matched: list[tuple[JMdictEntry, str]] = []  # (entry, jlpt_level)
    unmatched: list[tuple[str, str, str]] = []  # (expression, reading, level)
    seen_ent_seqs: set[str] = set()  # deduplicate by JMdict entry

    for (expression, reading), level in jlpt_words.items():
        entry = word_lookup.get((expression, reading))
        if entry is None:
            # Try with just the expression and any reading
            for key, e in word_lookup.items():
                if key[0] == expression:
                    entry = e
                    break

        if entry is not None:
            if entry.ent_seq not in seen_ent_seqs:
                seen_ent_seqs.add(entry.ent_seq)
                matched.append((entry, level))
        else:
            unmatched.append((expression, reading, level))

    print(f"   Matched: {len(matched)}")
    print(f"   Unmatched: {len(unmatched)}")

    # Count by level
    by_level: dict[str, int] = {}
    for _, level in matched:
        by_level[level] = by_level.get(level, 0) + 1
    for level in ["N5", "N4", "N3", "N2", "N1"]:
        print(f"     {level}: {by_level.get(level, 0)}")

    if unmatched:
        print(f"\n   Sample unmatched words:")
        for expr, reading, level in unmatched[:10]:
            print(f"     {expr} ({reading}) [{level}]")
        if len(unmatched) > 10:
            print(f"     ... and {len(unmatched) - 10} more")

    # Step 4: Generate documents
    print("\n4. Building vocabulary documents...")
    documents: list[dict] = []
    for entry, level in matched:
        doc = create_vocabulary_document(entry, level)
        if doc["meanings"]:  # Skip entries with no meanings
            documents.append(doc)

    print(f"   Generated {len(documents)} documents")

    # Step 5: Write files
    print("\n5. Preparing document files...")
    new_documents: dict[str, dict] = {}
    for doc in documents:
        filename = f"{doc['$id']}.json"
        new_documents[filename] = doc

    # Compare with existing
    VOCABULARY_DOCS.mkdir(parents=True, exist_ok=True)
    existing_files = set(f.name for f in VOCABULARY_DOCS.glob("*.json"))
    new_files = set(new_documents.keys())

    to_create = new_files - existing_files
    to_update = new_files & existing_files
    to_delete = existing_files - new_files

    print(f"   New: {len(to_create)}")
    print(f"   Existing: {len(to_update)}")
    print(f"   Stale: {len(to_delete)}")

    if args.dry_run:
        print("\n6. DRY RUN - no files modified")
        if to_create:
            for f in sorted(to_create)[:10]:
                print(f"   Would create: {f}")
            if len(to_create) > 10:
                print(f"   ... and {len(to_create) - 10} more")
        if to_delete:
            for f in sorted(to_delete)[:10]:
                print(f"   Would delete: {f}")
            if len(to_delete) > 10:
                print(f"   ... and {len(to_delete) - 10} more")
    else:
        print("\n6. Writing files...")

        created = 0
        updated = 0
        for filename, doc in new_documents.items():
            filepath = VOCABULARY_DOCS / filename
            was_new = not filepath.exists()
            if write_json_document(doc, filepath):
                if was_new:
                    created += 1
                else:
                    updated += 1

        deleted = 0
        for filename in to_delete:
            filepath = VOCABULARY_DOCS / filename
            if delete_json_document(filepath):
                deleted += 1

        print(f"   Created: {created}")
        print(f"   Updated: {updated}")
        print(f"   Deleted: {deleted}")

    # Summary
    print("\n" + "=" * 50)
    print("Summary:")
    print(f"  Total vocabulary documents: {len(documents)}")
    for level in ["N5", "N4", "N3", "N2", "N1"]:
        count = sum(1 for d in documents if d["jlptLevel"] == level)
        print(f"  {level}: {count}")

    print("\nDone.")


if __name__ == "__main__":
    main()
