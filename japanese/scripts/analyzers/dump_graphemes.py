#!/usr/bin/env python3
"""
Dump all grapheme documents to a text file for review.
Sorted by stroke count first, then Unicode codepoint.
"""

import sys
from pathlib import Path

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import REPORTS_DIR
from lib.grapheme_io import load_graphemes_sorted


def main():
    output_file = REPORTS_DIR / 'graphemes_all.txt'

    # Load all documents, sorted by (strokeCount, unicode)
    docs = load_graphemes_sorted()

    # Ensure output directory exists
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # Write to file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"Japanese Grapheme Dataset — {len(docs)} entries (sorted by stroke count)\n")
        f.write("=" * 60 + "\n\n")

        for doc in docs:
            unicode_id = doc.get('unicode', doc['$id'].replace('grapheme:', ''))
            symbol = doc.get('symbol', '?')
            name = doc.get('name', '')
            strokes = doc.get('strokeCount', '')
            variants = doc.get('variants', [])

            f.write(f"{unicode_id}  {symbol}  {name}\n")
            f.write(f"  strokes: {strokes}\n")

            if variants:
                variant_strs = []
                for v in variants:
                    v_symbol = v.get('symbol', '?')
                    v_unicode = v.get('unicode', v.get('$id', ''))
                    if v_unicode:
                        variant_strs.append(f"{v_symbol} ({v_unicode})")
                    else:
                        variant_strs.append(v_symbol)
                f.write(f"  variants: {', '.join(variant_strs)}\n")

            f.write("\n")

    print(f"Written {len(docs)} graphemes to {output_file}")


if __name__ == '__main__':
    main()
