#!/usr/bin/env python3
"""
kana_learning_order_generator.py

Generates a learning-order document for Japanese kana.

Ordering strategy:
- Hiragana base (gojuuon order) → hiragana dakuten → hiragana handakuten →
  katakana base → katakana dakuten → katakana handakuten → katakana extra

Within each group, characters follow standard gojuuon (五十音) row order:
a-row, ka-row, sa-row, ta-row, na-row, ha-row, ma-row, ya-row, ra-row, wa-row, n.

No inter-kana dependencies exist, so no dependency validation is needed.

Usage:
    python generators/kana_learning_order_generator.py [--dry-run]
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import KANA_DOCS, LEARNING_ORDER_DOCS
from lib.grapheme_io import write_json_document


# ---------------------------------------------------------------------------
# Kana Loading
# ---------------------------------------------------------------------------

def load_kana(docs_dir: Path = KANA_DOCS) -> dict[str, dict]:
    """
    Load all kana documents.

    Returns:
        Dict mapping $id -> document
    """
    kana: dict[str, dict] = {}

    for json_file in docs_dir.glob("*.json"):
        with open(json_file, "r", encoding="utf-8") as f:
            doc = json.load(f)
            kana[doc["$id"]] = doc

    return kana


# ---------------------------------------------------------------------------
# Ordering
# ---------------------------------------------------------------------------

# Canonical gojuuon order for sorting. Each character maps to its position.
# This defines the standard Japanese syllabary order.
GOJUUON_ORDER_HIRAGANA = [
    # Basic (46)
    "あ", "い", "う", "え", "お",
    "か", "き", "く", "け", "こ",
    "さ", "し", "す", "せ", "そ",
    "た", "ち", "つ", "て", "と",
    "な", "に", "ぬ", "ね", "の",
    "は", "ひ", "ふ", "へ", "ほ",
    "ま", "み", "む", "め", "も",
    "や", "ゆ", "よ",
    "ら", "り", "る", "れ", "ろ",
    "わ", "を",
    "ん",
    # Dakuten (20)
    "が", "ぎ", "ぐ", "げ", "ご",
    "ざ", "じ", "ず", "ぜ", "ぞ",
    "だ", "ぢ", "づ", "で", "ど",
    "ば", "び", "ぶ", "べ", "ぼ",
    # Handakuten (5)
    "ぱ", "ぴ", "ぷ", "ぺ", "ぽ",
]

GOJUUON_ORDER_KATAKANA = [
    # Basic (46)
    "ア", "イ", "ウ", "エ", "オ",
    "カ", "キ", "ク", "ケ", "コ",
    "サ", "シ", "ス", "セ", "ソ",
    "タ", "チ", "ツ", "テ", "ト",
    "ナ", "ニ", "ヌ", "ネ", "ノ",
    "ハ", "ヒ", "フ", "ヘ", "ホ",
    "マ", "ミ", "ム", "メ", "モ",
    "ヤ", "ユ", "ヨ",
    "ラ", "リ", "ル", "レ", "ロ",
    "ワ", "ヲ",
    "ン",
    # Dakuten (20)
    "ガ", "ギ", "グ", "ゲ", "ゴ",
    "ザ", "ジ", "ズ", "ゼ", "ゾ",
    "ダ", "ヂ", "ヅ", "デ", "ド",
    "バ", "ビ", "ブ", "ベ", "ボ",
    # Handakuten (5)
    "パ", "ピ", "プ", "ペ", "ポ",
    # Extra (1)
    "ヴ",
]


def codepoint_str(char: str) -> str:
    """Convert a character to a Unicode codepoint string."""
    return f"U+{ord(char):04X}"


def compute_order(kana: dict[str, dict]) -> list[str]:
    """
    Compute the learning order for kana.

    Hiragana first (gojuuon order), then katakana (gojuuon order).

    Returns:
        Ordered list of kana $ids
    """
    # Build symbol -> $id mapping
    symbol_to_id: dict[str, str] = {}
    for kid, doc in kana.items():
        symbol_to_id[doc["symbol"]] = kid

    ordered: list[str] = []

    # Hiragana in gojuuon order
    for char in GOJUUON_ORDER_HIRAGANA:
        kid = symbol_to_id.get(char)
        if kid:
            ordered.append(kid)
        else:
            print(f"  WARNING: hiragana '{char}' not found in documents")

    # Katakana in gojuuon order
    for char in GOJUUON_ORDER_KATAKANA:
        kid = symbol_to_id.get(char)
        if kid:
            ordered.append(kid)
        else:
            print(f"  WARNING: katakana '{char}' not found in documents")

    # Check for any kana documents not in the order
    ordered_set = set(ordered)
    for kid in kana:
        if kid not in ordered_set:
            print(f"  WARNING: kana '{kid}' not included in learning order")

    return ordered


# ---------------------------------------------------------------------------
# Document Generation
# ---------------------------------------------------------------------------

def create_learning_order_document(ordered: list[str]) -> dict:
    """
    Create a learning-order OSMF document for kana.

    Args:
        ordered: Ordered list of kana $ids

    Returns:
        Learning order document dict
    """
    return {
        "$schema": "../../../../shared-models/learning-order.schema.json",
        "$id": "japanese-kana-learning-order-default",
        "connectors": {
            "item": {}
        },
        "data": {
            "contentType": "kana",
            "trackId": "default",
            "trackName": "Default Kana Order",
            "source": "Generated: hiragana gojuuon order (base, dakuten, handakuten), then katakana in same order, plus katakana extra."
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

def main():
    parser = argparse.ArgumentParser(description="Generate kana learning order document")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without writing files")
    args = parser.parse_args()

    print("Generating Kana Learning Order")
    print("=" * 40)

    # Step 1: Load kana
    print("\n1. Loading kana documents...")
    kana = load_kana()
    print(f"   Loaded {len(kana)} kana")

    hiragana_count = sum(1 for d in kana.values() if d["type"] == "hiragana")
    katakana_count = sum(1 for d in kana.values() if d["type"] == "katakana")
    print(f"   Hiragana: {hiragana_count}, Katakana: {katakana_count}")

    # Step 2: Compute order
    print("\n2. Computing order...")
    ordered = compute_order(kana)
    print(f"   Ordered {len(ordered)} kana")

    # Show first/last few
    print(f"\n   First 10:")
    for i, kid in enumerate(ordered[:10]):
        doc = kana.get(kid, {})
        print(f"     {i:3d}. {doc.get('symbol', '?')}  {doc.get('romaji', '?'):<6s}  ({doc.get('type', '?')})")

    print(f"\n   Last 10:")
    for i, kid in enumerate(ordered[-10:], len(ordered) - 10):
        doc = kana.get(kid, {})
        print(f"     {i:3d}. {doc.get('symbol', '?')}  {doc.get('romaji', '?'):<6s}  ({doc.get('type', '?')})")

    # Step 3: Generate document
    print("\n3. Generating learning order document...")
    doc = create_learning_order_document(ordered)

    filename = "japanese-kana-learning-order-default.json"
    filepath = LEARNING_ORDER_DOCS / filename

    if args.dry_run:
        print(f"   DRY RUN - would write {filepath}")
    else:
        LEARNING_ORDER_DOCS.mkdir(parents=True, exist_ok=True)
        if write_json_document(doc, filepath):
            print(f"   Written: {filepath.name}")
        else:
            print(f"   Unchanged: {filepath.name}")

    # Summary
    print("\n" + "=" * 40)
    print("Summary:")
    print(f"  Total kana ordered: {len(ordered)}")
    print(f"  Hiragana: {hiragana_count}")
    print(f"  Katakana: {katakana_count}")

    print("\nDone.")


if __name__ == "__main__":
    main()
