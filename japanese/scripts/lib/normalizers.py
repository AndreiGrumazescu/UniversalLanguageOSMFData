#!/usr/bin/env python3
"""
Normalization strategies for kanji component comparison.

Each normalizer is a function that takes a character and returns its normalized form.
"""

import unicodedata
from typing import Callable

# Type alias for normalizer functions
Normalizer = Callable[[str], str]

# CJK Radicals Supplement mappings (U+2E80-2EFF)
# Only include mappings where visual form is essentially identical
CJK_RAD_SUPP_MAP = {
    # Heart variants -> 忄
    0x2E96: '忄',  # ⺖ HEART ONE
    0x2E97: '忄',  # ⺗ HEART TWO

    # Dog -> 犭
    0x2EA8: '犭',  # ⺨ DOG

    # Sheep/Ram/Ewe -> 羊
    0x2EB6: '羊',  # ⺶ SHEEP
    0x2EB7: '羊',  # ⺷ RAM
    0x2EB8: '羊',  # ⺸ EWE

    # Walk variants -> 辶
    0x2ECC: '辶',  # ⻌ SIMPLIFIED WALK
    0x2ECD: '辶',  # ⻍ WALK ONE
    0x2ECE: '辶',  # ⻎ WALK TWO

    # Ear radical (city/mound) -> 阝
    0x2ECF: '阝',  # ⻏ CITY
    0x2ED6: '阝',  # ⻖ MOUND TWO

    # Eat variants -> 食
    0x2EDE: '食',  # ⻞ EAT TWO
    0x2EDF: '食',  # ⻟ EAT THREE
    0x2EE0: '食',  # ⻠ C-SIMPLIFIED EAT

    # NOT normalized - visually different:
    # 0x2E84 ⺄ SECOND - different shape from 乙
    # 0x2E86 ⺆ BOX - different from 匚
    # 0x2E8C ⺌ SMALL ONE - missing strokes vs 小
    # 0x2E8D ⺍ SMALL TWO - missing strokes vs 小
}


def nfkc(char: str) -> str:
    """
    Standard Unicode NFKC normalization, applied repeatedly until stable.

    Handles:
    - Kangxi Radicals (U+2F00-2FDF) -> base CJK characters
    - CJK Compatibility Ideographs -> base CJK characters

    Does NOT handle:
    - CJK Radicals Supplement (U+2E80-2EFF) - these stay as-is
    """
    if len(char) != 1:
        return char

    seen = {char}
    result = char

    while True:
        normalized = unicodedata.normalize('NFKC', result)
        if normalized == result or normalized in seen:
            return result
        seen.add(normalized)
        result = normalized


def nfkc_plus(char: str) -> str:
    """
    NFKC plus manual mappings for CJK Radicals Supplement (U+2E80-2EFF).

    These are positional variants that NFKC doesn't handle.
    Maps them to their base CJK forms where the visual form is identical.
    """
    # First apply NFKC
    result = nfkc(char)

    if len(result) != 1:
        return result

    cp = ord(result)

    if cp in CJK_RAD_SUPP_MAP:
        return CJK_RAD_SUPP_MAP[cp]

    return result


# Registry of available normalizers
NORMALIZERS: dict[str, Normalizer] = {
    'nfkc_plus': nfkc_plus,
}


def get_normalizer(name: str) -> Normalizer:
    """Get a normalizer function by name."""
    if name not in NORMALIZERS:
        raise ValueError(f"Unknown normalizer: {name}. Available: {list(NORMALIZERS.keys())}")
    return NORMALIZERS[name]


# ---------------------------------------------------------------------------
# Grapheme-Aware Normalizer Factory
# ---------------------------------------------------------------------------

def make_grapheme_normalizer(variant_to_symbol: dict[str, str]) -> Normalizer:
    """
    Create a normalizer that applies nfkc_plus AND grapheme variant mappings.

    This ensures that variant symbols (like 匚) get normalized to their
    canonical form (匸) before processing.

    Args:
        variant_to_symbol: Dict mapping variant symbol -> canonical symbol

    Returns:
        A normalizer function that applies both nfkc_plus and variant mapping
    """
    def normalize(char: str) -> str:
        # First apply Unicode normalization
        result = nfkc_plus(char)
        # Then apply grapheme variant mappings
        return variant_to_symbol.get(result, result)

    return normalize


if __name__ == "__main__":
    # Test normalizers
    test_chars = [
        ('⼝', 'Kangxi radical mouth'),
        ('⻌', 'CJK Rad Supp walk'),
        ('⻖', 'CJK Rad Supp mound'),
        ('⺷', 'CJK Rad Supp ram'),
        ('口', 'mouth kanji'),
    ]

    print("Normalizer Comparison")
    print("=" * 60)

    print(f"{'Char':<6}", end="")
    for name in NORMALIZERS:
        print(f"{name:<12}", end="")
    print("Description")
    print("-" * 60)

    for char, desc in test_chars:
        print(f"{char:<6}", end="")
        for name, normalizer in NORMALIZERS.items():
            result = normalizer(char)
            print(f"{result:<12}", end="")
        print(desc)
