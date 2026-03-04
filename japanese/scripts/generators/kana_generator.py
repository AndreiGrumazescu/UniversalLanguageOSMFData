#!/usr/bin/env python3
"""
kana_generator.py

Generates OSMF data documents for all standard Japanese kana (hiragana and katakana).

Includes:
- 46 basic hiragana + 46 basic katakana
- 20 dakuten (voiced) hiragana + 20 dakuten katakana
- 5 handakuten (half-voiced) hiragana + 5 handakuten katakana
- 1 katakana-only character (vu)

Usage:
    python generators/kana_generator.py [--dry-run]
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import KANA_DOCS
from lib.grapheme_io import write_json_document, delete_json_document


# ---------------------------------------------------------------------------
# Kana Data Tables
# ---------------------------------------------------------------------------

# Each entry: (character, romaji)
# Unicode codepoint is derived from the character at runtime.

HIRAGANA_BASIC = [
    ("あ", "a"), ("い", "i"), ("う", "u"), ("え", "e"), ("お", "o"),
    ("か", "ka"), ("き", "ki"), ("く", "ku"), ("け", "ke"), ("こ", "ko"),
    ("さ", "sa"), ("し", "shi"), ("す", "su"), ("せ", "se"), ("そ", "so"),
    ("た", "ta"), ("ち", "chi"), ("つ", "tsu"), ("て", "te"), ("と", "to"),
    ("な", "na"), ("に", "ni"), ("ぬ", "nu"), ("ね", "ne"), ("の", "no"),
    ("は", "ha"), ("ひ", "hi"), ("ふ", "fu"), ("へ", "he"), ("ほ", "ho"),
    ("ま", "ma"), ("み", "mi"), ("む", "mu"), ("め", "me"), ("も", "mo"),
    ("や", "ya"), ("ゆ", "yu"), ("よ", "yo"),
    ("ら", "ra"), ("り", "ri"), ("る", "ru"), ("れ", "re"), ("ろ", "ro"),
    ("わ", "wa"), ("を", "wo"),
    ("ん", "n"),
]

HIRAGANA_DAKUTEN = [
    ("が", "ga"), ("ぎ", "gi"), ("ぐ", "gu"), ("げ", "ge"), ("ご", "go"),
    ("ざ", "za"), ("じ", "ji"), ("ず", "zu"), ("ぜ", "ze"), ("ぞ", "zo"),
    ("だ", "da"), ("ぢ", "di"), ("づ", "du"), ("で", "de"), ("ど", "do"),
    ("ば", "ba"), ("び", "bi"), ("ぶ", "bu"), ("べ", "be"), ("ぼ", "bo"),
]

HIRAGANA_HANDAKUTEN = [
    ("ぱ", "pa"), ("ぴ", "pi"), ("ぷ", "pu"), ("ぺ", "pe"), ("ぽ", "po"),
]

KATAKANA_BASIC = [
    ("ア", "a"), ("イ", "i"), ("ウ", "u"), ("エ", "e"), ("オ", "o"),
    ("カ", "ka"), ("キ", "ki"), ("ク", "ku"), ("ケ", "ke"), ("コ", "ko"),
    ("サ", "sa"), ("シ", "shi"), ("ス", "su"), ("セ", "se"), ("ソ", "so"),
    ("タ", "ta"), ("チ", "chi"), ("ツ", "tsu"), ("テ", "te"), ("ト", "to"),
    ("ナ", "na"), ("ニ", "ni"), ("ヌ", "nu"), ("ネ", "ne"), ("ノ", "no"),
    ("ハ", "ha"), ("ヒ", "hi"), ("フ", "fu"), ("ヘ", "he"), ("ホ", "ho"),
    ("マ", "ma"), ("ミ", "mi"), ("ム", "mu"), ("メ", "me"), ("モ", "mo"),
    ("ヤ", "ya"), ("ユ", "yu"), ("ヨ", "yo"),
    ("ラ", "ra"), ("リ", "ri"), ("ル", "ru"), ("レ", "re"), ("ロ", "ro"),
    ("ワ", "wa"), ("ヲ", "wo"),
    ("ン", "n"),
]

KATAKANA_DAKUTEN = [
    ("ガ", "ga"), ("ギ", "gi"), ("グ", "gu"), ("ゲ", "ge"), ("ゴ", "go"),
    ("ザ", "za"), ("ジ", "ji"), ("ズ", "zu"), ("ゼ", "ze"), ("ゾ", "zo"),
    ("ダ", "da"), ("ヂ", "di"), ("ヅ", "du"), ("デ", "de"), ("ド", "do"),
    ("バ", "ba"), ("ビ", "bi"), ("ブ", "bu"), ("ベ", "be"), ("ボ", "bo"),
]

KATAKANA_HANDAKUTEN = [
    ("パ", "pa"), ("ピ", "pi"), ("プ", "pu"), ("ペ", "pe"), ("ポ", "po"),
]

KATAKANA_EXTRA = [
    ("ヴ", "vu"),
]


# ---------------------------------------------------------------------------
# Document Generation
# ---------------------------------------------------------------------------

def codepoint_str(char: str) -> str:
    """Convert a character to a Unicode codepoint string (e.g., 'U+3042')."""
    cp = ord(char)
    return f"U+{cp:04X}"


def create_kana_document(char: str, romaji: str, kana_type: str) -> dict:
    """
    Create a kana OSMF data document.

    Args:
        char: The kana character
        romaji: Romanized reading
        kana_type: 'hiragana' or 'katakana'

    Returns:
        Document dict
    """
    unicode = codepoint_str(char)
    return {
        "$id": f"kana:{unicode}",
        "symbol": char,
        "unicode": unicode,
        "type": kana_type,
        "romaji": romaji,
    }


def build_all_kana() -> list[dict]:
    """Build all kana documents from the lookup tables."""
    documents = []

    for table, kana_type in [
        (HIRAGANA_BASIC, "hiragana"),
        (HIRAGANA_DAKUTEN, "hiragana"),
        (HIRAGANA_HANDAKUTEN, "hiragana"),
        (KATAKANA_BASIC, "katakana"),
        (KATAKANA_DAKUTEN, "katakana"),
        (KATAKANA_HANDAKUTEN, "katakana"),
        (KATAKANA_EXTRA, "katakana"),
    ]:
        for char, romaji in table:
            doc = create_kana_document(char, romaji, kana_type)
            documents.append(doc)

    return documents


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate kana OSMF data documents")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without writing files")
    args = parser.parse_args()

    print("Generating Kana Documents")
    print("=" * 40)

    # Step 1: Build all kana documents
    print("\n1. Building kana documents...")
    documents = build_all_kana()

    hiragana_count = sum(1 for d in documents if d["type"] == "hiragana")
    katakana_count = sum(1 for d in documents if d["type"] == "katakana")
    print(f"   Hiragana: {hiragana_count}")
    print(f"   Katakana: {katakana_count}")
    print(f"   Total: {len(documents)}")

    # Step 2: Build new document set
    print("\n2. Preparing document files...")
    new_documents: dict[str, dict] = {}  # filename -> document

    for doc in documents:
        filename = f"{doc['$id']}.json"
        new_documents[filename] = doc

    # Step 3: Compare with existing documents
    print("\n3. Comparing with existing documents...")
    KANA_DOCS.mkdir(parents=True, exist_ok=True)

    existing_files = set(f.name for f in KANA_DOCS.glob("*.json"))
    new_files = set(new_documents.keys())

    to_create = new_files - existing_files
    to_update = new_files & existing_files
    to_delete = existing_files - new_files

    print(f"   New: {len(to_create)}")
    print(f"   Existing: {len(to_update)}")
    print(f"   Stale: {len(to_delete)}")

    # Step 4: Write/delete files
    if args.dry_run:
        print("\n4. DRY RUN - no files modified")
        if to_create:
            for f in sorted(to_create)[:10]:
                print(f"   Would create: {f}")
            if len(to_create) > 10:
                print(f"   ... and {len(to_create) - 10} more")
        if to_delete:
            for f in sorted(to_delete):
                print(f"   Would delete: {f}")
    else:
        print("\n4. Writing files...")

        created = 0
        updated = 0
        for filename, doc in new_documents.items():
            filepath = KANA_DOCS / filename
            was_new = not filepath.exists()
            if write_json_document(doc, filepath):
                if was_new:
                    created += 1
                else:
                    updated += 1

        deleted = 0
        for filename in to_delete:
            filepath = KANA_DOCS / filename
            if delete_json_document(filepath):
                deleted += 1

        print(f"   Created: {created}")
        print(f"   Updated: {updated}")
        print(f"   Deleted: {deleted}")

    # Summary
    print("\n" + "=" * 40)
    print("Summary:")
    print(f"  Total kana documents: {len(documents)}")
    print(f"  Hiragana: {hiragana_count}")
    print(f"  Katakana: {katakana_count}")

    print("\nDone.")


if __name__ == "__main__":
    main()
