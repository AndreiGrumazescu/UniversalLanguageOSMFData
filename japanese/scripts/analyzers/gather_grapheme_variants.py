#!/usr/bin/env python3
"""
Gather all embedded variants from grapheme documents.
Outputs a markdown table for documentation.
"""

import sys
from pathlib import Path

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.grapheme_io import load_graphemes


def main():
    # Load all graphemes
    graphemes = load_graphemes()

    # Collect all graphemes with embedded variants
    variants_data = []

    for gid, doc in sorted(graphemes.items()):
        if 'variants' in doc and doc['variants']:
            canonical_unicode = doc.get('unicode', gid.replace('grapheme:', ''))
            canonical_symbol = doc.get('symbol', '?')
            canonical_name = doc.get('name', '')

            for variant in doc['variants']:
                variant_unicode = variant.get('unicode', '')
                variant_symbol = variant.get('symbol', '?')
                variant_name = variant.get('name', '')

                variants_data.append({
                    'canonical_unicode': canonical_unicode,
                    'canonical_symbol': canonical_symbol,
                    'canonical_name': canonical_name,
                    'variant_unicode': variant_unicode,
                    'variant_symbol': variant_symbol,
                    'variant_name': variant_name,
                })

    # Print markdown table
    print("| Canonical | Symbol | Name | Variant | Symbol | Variant Name |")
    print("|-----------|--------|------|---------|--------|--------------|")

    for v in variants_data:
        variant_u = v['variant_unicode'] if v['variant_unicode'] else '-'
        variant_n = v['variant_name'] if v['variant_name'] else '-'
        print(f"| {v['canonical_unicode']} | {v['canonical_symbol']} | {v['canonical_name']} | {variant_u} | {v['variant_symbol']} | {variant_n} |")

    print(f"\nTotal: {len(variants_data)} embedded variants in grapheme documents")


if __name__ == '__main__':
    main()
