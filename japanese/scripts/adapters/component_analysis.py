#!/usr/bin/env python3
"""
component_analysis.py

Shared module for kanji component decomposition using CHISE IDS (primary)
and KanjiVG (fallback). Used by:
- analyze_component_popularity.py
- regenerate_grapheme_dependencies.py

This module provides functions to:
1. Load CHISE IDS data
2. Load KanjiVG index
3. Extract components from a character using CHISE or KanjiVG
"""

import json
import re
import sys
from pathlib import Path
from typing import Callable

# ---------------------------------------------------------------------------
# Path Configuration (from shared module)
# ---------------------------------------------------------------------------

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import KANJIVG_DIR, KVG_INDEX_PATH, KVG_KANJI_DIR, CHISE_IDS_PATH

# Add kanjivg module to path for imports
sys.path.insert(0, str(KANJIVG_DIR))

from utils import SvgFileInfo
from kanjivg import StrokeGr

# ---------------------------------------------------------------------------
# IDS (Ideographic Description Sequence) Constants
# ---------------------------------------------------------------------------

# Unicode Ideographic Description Characters (U+2FF0-U+2FFF)
# These operators describe how components are spatially arranged
IDS_OPERATORS = set(chr(c) for c in range(0x2FF0, 0x3000))


# ---------------------------------------------------------------------------
# CHISE IDS Loading and Parsing
# ---------------------------------------------------------------------------

def load_chise_ids(path: Path = CHISE_IDS_PATH) -> dict[str, str]:
    """
    Load CHISE IDS file and return mapping of char -> IDS string.

    File format: U+XXXX<TAB>char<TAB>IDS[@apparent=IDS]
    """
    char_to_ids: dict[str, str] = {}

    if not path.exists():
        return char_to_ids

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(";"):
                continue

            parts = line.split("\t")
            if len(parts) >= 3:
                char = parts[1]
                ids = parts[2]
                # Remove @apparent suffix if present
                if "@apparent=" in ids:
                    ids = ids.split("@apparent=")[0].strip()
                char_to_ids[char] = ids

    return char_to_ids


def extract_ids_components(ids: str) -> set[str]:
    """
    Extract component characters from an IDS string.

    Filters out:
    - IDS operator characters (⿰, ⿱, etc.)
    - Entity references like &CDP-XXXX; or &M-XXXXX;
    - Whitespace and non-CJK characters

    Returns:
        Set of unique component characters.
    """
    components = set()

    # Remove entity references like &CDP-XXXX; or &M-XXXXX;
    ids_clean = re.sub(r'&[^;]+;', '', ids)

    for char in ids_clean:
        # Skip IDS operators
        if char in IDS_OPERATORS:
            continue
        # Skip whitespace and low codepoints (punctuation, ASCII, etc.)
        if char.isspace() or ord(char) < 0x2E80:
            continue
        components.add(char)

    return components


# Cache for CHISE IDS components
_chise_cache: dict[str, set[str]] = {}


def get_chise_components(char: str, chise_ids: dict[str, str]) -> set[str]:
    """
    Get components of a character from CHISE IDS data.

    Args:
        char: The character to decompose
        chise_ids: Dict mapping char -> IDS string

    Returns:
        Set of component characters (may be empty if char == its IDS)
    """
    global _chise_cache

    if char in _chise_cache:
        return _chise_cache[char]

    if char not in chise_ids:
        _chise_cache[char] = set()
        return set()

    ids = chise_ids[char]
    components = extract_ids_components(ids)

    # If the only "component" is the character itself, it's atomic
    # (e.g., 一 has IDS "一" - no real decomposition)
    if components == {char}:
        _chise_cache[char] = set()
        return set()

    # Remove the character itself from components (shouldn't be its own component)
    components.discard(char)

    _chise_cache[char] = components
    return components


def clear_chise_cache():
    """Clear the CHISE components cache."""
    global _chise_cache
    _chise_cache = {}


# ---------------------------------------------------------------------------
# KanjiVG Index Loading
# ---------------------------------------------------------------------------

def load_kanjivg_index(path: Path = KVG_INDEX_PATH) -> set[str]:
    """
    Load kvg-index.json and return set of all characters with SVG files.
    """
    with open(path, "r", encoding="utf-8") as f:
        index = json.load(f)
    return set(index.keys())


# ---------------------------------------------------------------------------
# KanjiVG Component Extraction
# ---------------------------------------------------------------------------

# Cache for parsed KanjiVG files
_kanjivg_cache: dict[str, set[str]] = {}


def get_kanjivg_components(char: str, kanjivg_chars: set[str]) -> set[str]:
    """
    Get direct child components of a kanji from KanjiVG.

    Args:
        char: The kanji character
        kanjivg_chars: Set of chars in KanjiVG (for quick existence check)

    Returns:
        Set of unique direct child component characters (may be empty)
    """
    global _kanjivg_cache

    if char in _kanjivg_cache:
        return _kanjivg_cache[char]

    if char not in kanjivg_chars:
        _kanjivg_cache[char] = set()
        return set()

    try:
        code = f"{ord(char):05x}"
        sfi = SvgFileInfo(f"{code}.svg", str(KVG_KANJI_DIR))
        if not sfi.OK:
            _kanjivg_cache[char] = set()
            return set()

        kanji = sfi.read()
        if kanji and kanji.strokes:
            # Get direct children using simplified=True for canonical forms
            # Return as SET to deduplicate (e.g., 林 has 木 twice, but count once)
            components = set(kanji.strokes.components(simplified=True, recursive=False))
            _kanjivg_cache[char] = components
            return components
    except Exception:
        # Silently handle parsing errors
        pass

    _kanjivg_cache[char] = set()
    return set()


def clear_kanjivg_cache():
    """Clear the KanjiVG components cache."""
    global _kanjivg_cache
    _kanjivg_cache = {}


# ---------------------------------------------------------------------------
# Unified Component Extraction (CHISE primary, KanjiVG fallback)
# ---------------------------------------------------------------------------

def get_library_status(
    char: str,
    chise_ids: dict[str, str],
    kanjivg_chars: set[str],
    normalizer: Callable[[str], str],
) -> tuple[str, str]:
    """
    Determine the status of a character in both CHISE and KanjiVG.

    Returns:
        Tuple of (chise_status, kanjivg_status) where each is "decomposed", "atomic", or "none"
    """
    normalized = normalizer(char)

    # CHISE status
    chise_status = "none"
    if char in chise_ids or normalized in chise_ids:
        # Character exists in CHISE - check if it has components
        chise_orig = get_chise_components(char, chise_ids)
        chise_norm = get_chise_components(normalized, chise_ids) if char != normalized else set()
        if chise_orig or chise_norm:
            chise_status = "decomposed"
        else:
            chise_status = "atomic"

    # KanjiVG status
    kanjivg_status = "none"
    if char in kanjivg_chars or normalized in kanjivg_chars:
        # Character exists in KanjiVG - check if it has components
        kvg_orig = get_kanjivg_components(char, kanjivg_chars)
        kvg_norm = get_kanjivg_components(normalized, kanjivg_chars) if char != normalized else set()
        if kvg_orig or kvg_norm:
            kanjivg_status = "decomposed"
        else:
            kanjivg_status = "atomic"

    return chise_status, kanjivg_status


def get_components(
    char: str,
    chise_ids: dict[str, str],
    kanjivg_chars: set[str],
    normalizer: Callable[[str], str],
) -> tuple[set[str], str]:
    """
    Get components for a character, trying CHISE first, then KanjiVG.

    Args:
        char: Original character
        chise_ids: CHISE IDS data
        kanjivg_chars: Set of chars with KanjiVG data
        normalizer: Normalization function

    Returns:
        Tuple of (components_set, source) where source is:
        "chise", "kanjivg", "chise-atomic", "kanjivg-atomic", or "none"
    """
    normalized = normalizer(char)

    # Try CHISE first (for both original and normalized)
    chise_orig = get_chise_components(char, chise_ids)
    chise_norm = get_chise_components(normalized, chise_ids) if char != normalized else set()

    # Use whichever CHISE result is larger
    chise_components = chise_orig if len(chise_orig) >= len(chise_norm) else chise_norm

    if chise_components:
        return chise_components, "chise"

    # Fall back to KanjiVG
    kvg_orig = get_kanjivg_components(char, kanjivg_chars)
    kvg_norm = get_kanjivg_components(normalized, kanjivg_chars) if char != normalized else set()

    # Use whichever KanjiVG result is larger
    kvg_components = kvg_orig if len(kvg_orig) >= len(kvg_norm) else kvg_norm

    if kvg_components:
        return kvg_components, "kanjivg"

    # No components found - determine if atomic or truly missing
    # Check if in CHISE (would be atomic since no components)
    if char in chise_ids or normalized in chise_ids:
        return set(), "chise-atomic"

    # Check if in KanjiVG (would be atomic since no components)
    if char in kanjivg_chars or normalized in kanjivg_chars:
        return set(), "kanjivg-atomic"

    return set(), "none"


# ---------------------------------------------------------------------------
# Convenience: Identity normalizer
# ---------------------------------------------------------------------------

def identity_normalizer(char: str) -> str:
    """Identity normalizer - returns character unchanged."""
    return char


# ---------------------------------------------------------------------------
# Expanded Component Extraction (Union of All Sources)
# ---------------------------------------------------------------------------

def get_all_components_expanded(
    char: str,
    chise_ids: dict[str, str],
    kanjivg_chars: set[str],
    normalizer: Callable[[str], str],
) -> set[str]:
    """
    Get ALL components for a character from ALL sources.

    This function combines results from:
    - CHISE(original)
    - CHISE(normalized)
    - KanjiVG(original)
    - KanjiVG(normalized)

    Args:
        char: Original character
        chise_ids: CHISE IDS data
        kanjivg_chars: Set of chars with KanjiVG data
        normalizer: Normalization function

    Returns:
        Set of all component characters (union of all sources)
    """
    normalized = normalizer(char)
    giant_set: set[str] = set()

    # CHISE: original
    giant_set.update(get_chise_components(char, chise_ids))

    # CHISE: normalized (if different)
    if char != normalized:
        giant_set.update(get_chise_components(normalized, chise_ids))

    # KanjiVG: original
    giant_set.update(get_kanjivg_components(char, kanjivg_chars))

    # KanjiVG: normalized (if different)
    if char != normalized:
        giant_set.update(get_kanjivg_components(normalized, kanjivg_chars))

    # Remove the character itself (shouldn't be its own component)
    giant_set.discard(char)
    giant_set.discard(normalized)

    return giant_set
