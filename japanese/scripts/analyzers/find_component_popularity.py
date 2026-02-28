#!/usr/bin/env python3
"""
analyze_component_popularity.py

Analyzes all kanji from kanjidic2.xml, tracks how often each normalized kanji
appears as a component in other kanji using CHISE IDS (primary) and KanjiVG
(fallback) decomposition data. Identifies which kanji are graphemes (base cases).

Outputs:
- Text report sorted by stroke count
- JSON data for HTML visualization

Usage:
    python analyze_component_popularity.py [--dry-run] [--skip-db]
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

# Lazy imports for optional database functionality
libsql = None
load_dotenv = None

def _ensure_db_imports():
    """Import database dependencies on demand."""
    global libsql, load_dotenv
    if libsql is None:
        try:
            import libsql_experimental as _libsql
            from dotenv import load_dotenv as _load_dotenv
            libsql = _libsql
            load_dotenv = _load_dotenv
        except ImportError as e:
            print(f"Error: Database dependencies not installed: {e}")
            print("Install with: pip install libsql-experimental python-dotenv")
            sys.exit(1)

# ---------------------------------------------------------------------------
# Path Configuration (from shared module)
# ---------------------------------------------------------------------------

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import REPORTS_DIR, TURSO_ENV_FILE

OUTPUT_TXT = REPORTS_DIR / "component-popularity.txt"
OUTPUT_JSON = REPORTS_DIR / "component-popularity.json"
OUTPUT_CANDIDATES = REPORTS_DIR / "grapheme-candidates.txt"
OUTPUT_GRAPHEME_POP = REPORTS_DIR / "grapheme-popularity.txt"

# ---------------------------------------------------------------------------
# Import shared modules
# ---------------------------------------------------------------------------

from adapters.component_analysis import (
    load_chise_ids,
    load_kanjivg_index,
    get_chise_components,
    get_kanjivg_components,
    get_library_status,
    get_components,
    get_all_components_expanded,
)

from adapters.kanjidic import parse_kanjidic

from lib.normalizers import make_grapheme_normalizer


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class KanjiEntry:
    """Represents a kanji with its analysis data."""
    original: str                     # Original kanji character from kanjidic2
    normalized: str                   # Normalized via nfkc_plus
    stroke_count: int                 # From kanjidic2.xml
    popularity: int = 0               # How many times used as component
    is_grapheme: bool = False         # True if exists in grapheme DB (primary or variant)
    chise_status: str = "none"        # "decomposed", "atomic", or "none"
    kanjivg_status: str = "none"      # "decomposed", "atomic", or "none"
    decomp_source: str = "none"       # "chise", "kanjivg", "chise-atomic", "kanjivg-atomic", or "none"
    grapheme_id: Optional[str] = None # The grapheme ID if is_grapheme is True


# ---------------------------------------------------------------------------
# Database Connection
# ---------------------------------------------------------------------------

def connect_db():
    """Load .env and connect to Turso."""
    _ensure_db_imports()
    load_dotenv(TURSO_ENV_FILE)
    url = os.environ.get("TURSO_DATABASE_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN")
    if not url or not token:
        print(f"Error: TURSO_DATABASE_URL and TURSO_AUTH_TOKEN must be set in {TURSO_ENV_FILE}")
        sys.exit(1)
    conn = libsql.connect(database=url, auth_token=token)
    return conn


def load_graphemes_from_turso(conn) -> tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, dict]]:
    """
    Load grapheme data from Turso database.

    Returns:
        tuple of (grapheme_primaries, variant_to_canonical, variant_to_symbol, grapheme_id_to_doc)
        - grapheme_primaries: maps symbol -> grapheme_id
        - variant_to_canonical: maps variant symbol -> grapheme_id
        - variant_to_symbol: maps variant symbol -> canonical symbol (for normalization)
        - grapheme_id_to_doc: maps grapheme_id -> document with variants
    """
    grapheme_primaries: dict[str, str] = {}
    grapheme_id_to_symbol: dict[str, str] = {}
    variant_to_canonical: dict[str, str] = {}
    grapheme_id_to_doc: dict[str, dict] = {}

    # Load primary graphemes
    rows = conn.execute("SELECT id, symbol FROM ja_data_grapheme").fetchall()
    for row in rows:
        grapheme_id, symbol = row[0], row[1]
        if symbol:
            grapheme_primaries[symbol] = grapheme_id
            grapheme_id_to_symbol[grapheme_id] = symbol
            grapheme_id_to_doc[grapheme_id] = {"symbol": symbol, "variants": []}

    # Load variants
    rows = conn.execute("SELECT grapheme_id, symbol FROM ja_data_grapheme_variant").fetchall()
    for row in rows:
        grapheme_id, symbol = row[0], row[1]
        if symbol:
            variant_to_canonical[symbol] = grapheme_id
            # Add variant to the grapheme's document
            if grapheme_id in grapheme_id_to_doc:
                grapheme_id_to_doc[grapheme_id]["variants"].append({"symbol": symbol})

    # Build variant symbol -> canonical symbol mapping
    variant_to_symbol: dict[str, str] = {}
    for variant_sym, grapheme_id in variant_to_canonical.items():
        canonical_sym = grapheme_id_to_symbol.get(grapheme_id)
        if canonical_sym:
            variant_to_symbol[variant_sym] = canonical_sym

    return grapheme_primaries, variant_to_canonical, variant_to_symbol, grapheme_id_to_doc




# ---------------------------------------------------------------------------
# Build Memoization Dict (First Pass)
# ---------------------------------------------------------------------------

def build_memoization_dict(
    kanjidic_entries: list[tuple[str, int]],
    grapheme_primaries: dict[str, str],
    variant_to_canonical: dict[str, str],
    chise_ids: dict[str, str],
    kanjivg_chars: set[str],
    normalizer: Callable[[str], str],
) -> dict[str, KanjiEntry]:
    """
    First pass: Build the memoization dictionary.

    For each kanji in kanjidic2:
    1. Normalize using nfkc_plus
    2. Create/update KanjiEntry keyed by normalized form
    3. If multiple kanji normalize to same form, keep lower stroke_count
    4. Set is_grapheme based on grapheme lookup
    5. Check decomposition sources (CHISE primary, KanjiVG fallback)
    6. Initialize popularity = 0 if has decomposition, -1 if not
    """
    kanji_dict: dict[str, KanjiEntry] = {}

    for kanji, stroke_count in kanjidic_entries:
        normalized = normalizer(kanji)

        # Check if already exists (collision)
        if normalized in kanji_dict:
            existing = kanji_dict[normalized]
            # Keep lower stroke count (represents simpler form)
            if stroke_count < existing.stroke_count:
                existing.original = kanji
                existing.stroke_count = stroke_count
        else:
            # Create new entry
            entry = KanjiEntry(
                original=kanji,
                normalized=normalized,
                stroke_count=stroke_count,
            )
            kanji_dict[normalized] = entry

        # Set flags (update every iteration to ensure correctness)
        entry = kanji_dict[normalized]

        # Check if in grapheme database
        if normalized in grapheme_primaries:
            entry.is_grapheme = True
            entry.grapheme_id = grapheme_primaries[normalized]
        elif normalized in variant_to_canonical:
            entry.is_grapheme = True
            entry.grapheme_id = variant_to_canonical[normalized]

        # Get status in both libraries
        chise_status, kanjivg_status = get_library_status(kanji, chise_ids, kanjivg_chars, normalizer)
        entry.chise_status = chise_status
        entry.kanjivg_status = kanjivg_status

        # Determine decomposition source (which library was used)
        components, source = get_components(kanji, chise_ids, kanjivg_chars, normalizer)
        entry.decomp_source = source

        # Initialize popularity to 0 for ALL entries
        # Even primitives with no decomposition can be components of other kanji
        entry.popularity = 0

    return kanji_dict


# ---------------------------------------------------------------------------
# Calculate Popularity (Second Pass)
# ---------------------------------------------------------------------------

def calculate_popularity(
    kanji_dict: dict[str, KanjiEntry],
    grapheme_primaries: dict[str, str],
    variant_to_canonical: dict[str, str],
    grapheme_id_to_doc: dict[str, dict],
    chise_ids: dict[str, str],
    kanjivg_chars: set[str],
    normalizer: Callable[[str], str],
) -> None:
    """
    Second pass: Calculate popularity by traversing component trees.

    Uses expanded search: union of CHISE + KanjiVG for both original and normalized.
    For grapheme components, also searches children of their variants.
    Stops recursion when popularity > 0 (already processed), not at graphemes.

    Mutates kanji_dict in place.
    """

    def get_expanded_children(char: str) -> set[str]:
        """
        Get ALL children using expanded search.
        If a child is a grapheme with variants, also get children of those variants.
        """
        # Get all components from all sources (CHISE + KanjiVG, original + normalized)
        giant_set = get_all_components_expanded(char, chise_ids, kanjivg_chars, normalizer)

        # For each component that is a grapheme, also get children of its variants
        expanded_set = set(giant_set)
        for comp in giant_set:
            normalized_comp = normalizer(comp)
            comp_gid = grapheme_primaries.get(normalized_comp) or variant_to_canonical.get(normalized_comp)
            if comp_gid and comp_gid in grapheme_id_to_doc:
                comp_doc = grapheme_id_to_doc[comp_gid]
                for variant in comp_doc.get("variants", []):
                    variant_symbol = variant.get("symbol")
                    if variant_symbol:
                        variant_children = get_all_components_expanded(variant_symbol, chise_ids, kanjivg_chars, normalizer)
                        expanded_set.update(variant_children)

        return expanded_set

    def process_children(char: str) -> None:
        """
        Process a character's children.
        For each child: increment popularity, recurse only if first time (popularity was 0).
        """
        children = get_expanded_children(char)

        for child in children:
            child_normalized = normalizer(child)
            entry = kanji_dict.get(child_normalized)

            if entry:
                was_zero = entry.popularity == 0
                entry.popularity += 1

                # Only recurse if this is the first time seeing this child
                if was_zero:
                    process_children(child)

    # Process each kanji entry
    print("  Processing kanji entries...")
    total = len(kanji_dict)
    processed = 0

    for entry in kanji_dict.values():
        process_children(entry.original)

        processed += 1
        if processed % 1000 == 0:
            print(f"    Processed {processed}/{total}...")


# ---------------------------------------------------------------------------
# Output Functions
# ---------------------------------------------------------------------------

def write_text_report(
    kanji_dict: dict[str, KanjiEntry],
    output_path: Path,
) -> None:
    """
    Write a text report sorted by stroke count, then by popularity descending.
    """
    # Group by stroke count
    by_strokes: dict[int, list[KanjiEntry]] = defaultdict(list)
    for entry in kanji_dict.values():
        by_strokes[entry.stroke_count].append(entry)

    # Sort each group by popularity descending
    for stroke_count in by_strokes:
        by_strokes[stroke_count].sort(key=lambda e: e.popularity, reverse=True)

    # Calculate stats
    total = len(kanji_dict)
    chise_decomp = sum(1 for e in kanji_dict.values() if e.chise_status == "decomposed")
    chise_atomic = sum(1 for e in kanji_dict.values() if e.chise_status == "atomic")
    kvg_decomp = sum(1 for e in kanji_dict.values() if e.kanjivg_status == "decomposed")
    kvg_atomic = sum(1 for e in kanji_dict.values() if e.kanjivg_status == "atomic")
    from_chise = sum(1 for e in kanji_dict.values() if e.decomp_source == "chise")
    from_chise_atomic = sum(1 for e in kanji_dict.values() if e.decomp_source == "chise-atomic")
    from_kanjivg = sum(1 for e in kanji_dict.values() if e.decomp_source == "kanjivg")
    from_kanjivg_atomic = sum(1 for e in kanji_dict.values() if e.decomp_source == "kanjivg-atomic")
    no_decomp = sum(1 for e in kanji_dict.values() if e.decomp_source == "none")
    graphemes = sum(1 for e in kanji_dict.values() if e.is_grapheme)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("Kanji Component Popularity Analysis\n")
        f.write("=" * 40 + "\n")
        f.write(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
        f.write(f"Total kanji in kanjidic2: {total}\n")
        f.write(f"\nLibrary Coverage:\n")
        f.write(f"  CHISE:   {chise_decomp + chise_atomic} total ({chise_decomp} decomposed, {chise_atomic} atomic)\n")
        f.write(f"  KanjiVG: {kvg_decomp + kvg_atomic} total ({kvg_decomp} decomposed, {kvg_atomic} atomic)\n")
        f.write(f"\nDecomposition Sources Used:\n")
        f.write(f"  chise:         {from_chise:>5} ({100*from_chise/total:.1f}%)\n")
        f.write(f"  chise-atomic:  {from_chise_atomic:>5} ({100*from_chise_atomic/total:.1f}%)\n")
        f.write(f"  kanjivg:       {from_kanjivg:>5} ({100*from_kanjivg/total:.1f}%)\n")
        f.write(f"  kanjivg-atomic:{from_kanjivg_atomic:>5} ({100*from_kanjivg_atomic/total:.1f}%)\n")
        f.write(f"  none:          {no_decomp:>5} ({100*no_decomp/total:.1f}%)\n")
        f.write(f"\nGraphemes defined: {graphemes}\n")
        f.write("\n")

        for stroke_count in sorted(by_strokes.keys()):
            entries = by_strokes[stroke_count]
            f.write(f"=== {stroke_count} Stroke{'s' if stroke_count != 1 else ''} ({len(entries)} entries) ===\n")

            for entry in entries:
                grapheme_flag = "YES" if entry.is_grapheme else "NO"
                # Show "other" library status in parentheses
                if entry.decomp_source.startswith("chise"):
                    other_status = f"(kvg: {entry.kanjivg_status})"
                elif entry.decomp_source.startswith("kanjivg"):
                    other_status = f"(chise: {entry.chise_status})"
                else:
                    other_status = ""
                f.write(f"{entry.normalized}  pop: {entry.popularity:>5}  grapheme: {grapheme_flag}  src: {entry.decomp_source:<13} {other_status}\n")

            f.write("\n")

    print(f"  Written to: {output_path}")


def write_candidates_report(
    kanji_dict: dict[str, KanjiEntry],
    output_path: Path,
) -> None:
    """
    Write a report of grapheme candidates: components that are NOT graphemes
    but have popularity > 0 (used as components in other kanji).

    Sorted by stroke count, then by popularity descending within each group.
    """
    # Filter to candidates: not a grapheme AND popularity > 0 AND atomic in at least one library
    candidates = [
        e for e in kanji_dict.values()
        if not e.is_grapheme
        and e.popularity > 0
        and (e.chise_status == "atomic" or e.kanjivg_status == "atomic")
    ]

    if not candidates:
        print("  No candidates found")
        return

    # Group by stroke count
    by_strokes: dict[int, list[KanjiEntry]] = defaultdict(list)
    for entry in candidates:
        by_strokes[entry.stroke_count].append(entry)

    # Sort each group by popularity descending
    for stroke_count in by_strokes:
        by_strokes[stroke_count].sort(key=lambda e: e.popularity, reverse=True)

    # Calculate stats for candidates
    total_candidates = len(candidates)
    chise_decomp = sum(1 for e in candidates if e.chise_status == "decomposed")
    chise_atomic = sum(1 for e in candidates if e.chise_status == "atomic")
    kvg_decomp = sum(1 for e in candidates if e.kanjivg_status == "decomposed")
    kvg_atomic = sum(1 for e in candidates if e.kanjivg_status == "atomic")
    from_chise = sum(1 for e in candidates if e.decomp_source == "chise")
    from_chise_atomic = sum(1 for e in candidates if e.decomp_source == "chise-atomic")
    from_kanjivg = sum(1 for e in candidates if e.decomp_source == "kanjivg")
    from_kanjivg_atomic = sum(1 for e in candidates if e.decomp_source == "kanjivg-atomic")
    no_decomp = sum(1 for e in candidates if e.decomp_source == "none")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("Grapheme Candidates Report\n")
        f.write("=" * 40 + "\n")
        f.write(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
        f.write(f"\nCriteria: is_grapheme=NO AND popularity>0 AND atomic in at least one library\n")
        f.write(f"Total candidates: {total_candidates}\n")
        f.write(f"\nLibrary Coverage (candidates only):\n")
        f.write(f"  CHISE:   {chise_decomp + chise_atomic} total ({chise_decomp} decomposed, {chise_atomic} atomic)\n")
        f.write(f"  KanjiVG: {kvg_decomp + kvg_atomic} total ({kvg_decomp} decomposed, {kvg_atomic} atomic)\n")
        f.write(f"\nDecomposition Sources:\n")
        f.write(f"  chise:         {from_chise:>5} ({100*from_chise/total_candidates:.1f}%)\n")
        f.write(f"  chise-atomic:  {from_chise_atomic:>5} ({100*from_chise_atomic/total_candidates:.1f}%)\n")
        f.write(f"  kanjivg:       {from_kanjivg:>5} ({100*from_kanjivg/total_candidates:.1f}%)\n")
        f.write(f"  kanjivg-atomic:{from_kanjivg_atomic:>5} ({100*from_kanjivg_atomic/total_candidates:.1f}%)\n")
        f.write(f"  none:          {no_decomp:>5} ({100*no_decomp/total_candidates:.1f}%)\n")
        f.write("\n")

        for stroke_count in sorted(by_strokes.keys()):
            entries = by_strokes[stroke_count]
            f.write(f"=== {stroke_count} Stroke{'s' if stroke_count != 1 else ''} ({len(entries)} candidates) ===\n")

            for entry in entries:
                # Show "other" library status in parentheses
                if entry.decomp_source.startswith("chise"):
                    other_status = f"(kvg: {entry.kanjivg_status})"
                elif entry.decomp_source.startswith("kanjivg"):
                    other_status = f"(chise: {entry.chise_status})"
                else:
                    other_status = ""

                f.write(f"{entry.normalized}  pop: {entry.popularity:>5}  src: {entry.decomp_source:<13} {other_status}\n")

            f.write("\n")

    print(f"  Written to: {output_path}")


def write_grapheme_popularity_report(
    kanji_dict: dict[str, KanjiEntry],
    output_path: Path,
) -> None:
    """
    Write a report of grapheme popularity, sorted by stroke count (highest first),
    then by popularity descending within each group.
    """
    # Filter to graphemes only
    graphemes = [e for e in kanji_dict.values() if e.is_grapheme]

    if not graphemes:
        print("  No graphemes found")
        return

    # Group by stroke count
    by_strokes: dict[int, list[KanjiEntry]] = defaultdict(list)
    for entry in graphemes:
        by_strokes[entry.stroke_count].append(entry)

    # Sort each group by popularity descending
    for stroke_count in by_strokes:
        by_strokes[stroke_count].sort(key=lambda e: e.popularity, reverse=True)

    # Calculate stats
    total_graphemes = len(graphemes)
    from_chise = sum(1 for e in graphemes if e.decomp_source == "chise")
    from_chise_atomic = sum(1 for e in graphemes if e.decomp_source == "chise-atomic")
    from_kanjivg = sum(1 for e in graphemes if e.decomp_source == "kanjivg")
    from_kanjivg_atomic = sum(1 for e in graphemes if e.decomp_source == "kanjivg-atomic")
    no_decomp = sum(1 for e in graphemes if e.decomp_source == "none")
    total_popularity = sum(e.popularity for e in graphemes)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("Grapheme Popularity Report\n")
        f.write("=" * 40 + "\n")
        f.write(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
        f.write(f"\nTotal graphemes: {total_graphemes}\n")
        f.write(f"Total popularity (sum): {total_popularity:,}\n")
        f.write(f"\nDecomposition Sources:\n")
        f.write(f"  chise:          {from_chise:>5} ({100*from_chise/total_graphemes:.1f}%)\n")
        f.write(f"  chise-atomic:   {from_chise_atomic:>5} ({100*from_chise_atomic/total_graphemes:.1f}%)\n")
        f.write(f"  kanjivg:        {from_kanjivg:>5} ({100*from_kanjivg/total_graphemes:.1f}%)\n")
        f.write(f"  kanjivg-atomic: {from_kanjivg_atomic:>5} ({100*from_kanjivg_atomic/total_graphemes:.1f}%)\n")
        f.write(f"  none:           {no_decomp:>5} ({100*no_decomp/total_graphemes:.1f}%)\n")
        f.write("\n")

        # Sort by stroke count DESCENDING (highest first)
        for stroke_count in sorted(by_strokes.keys(), reverse=True):
            entries = by_strokes[stroke_count]
            f.write(f"=== {stroke_count} Stroke{'s' if stroke_count != 1 else ''} ({len(entries)} graphemes) ===\n")

            for entry in entries:
                # Show "other" library status in parentheses
                if entry.decomp_source.startswith("chise"):
                    other_status = f"(kvg: {entry.kanjivg_status})"
                elif entry.decomp_source.startswith("kanjivg"):
                    other_status = f"(chise: {entry.chise_status})"
                else:
                    other_status = ""

                f.write(f"{entry.normalized}  pop: {entry.popularity:>5}  src: {entry.decomp_source:<13} {other_status}\n")

            f.write("\n")

    print(f"  Written to: {output_path}")


def generate_json_output(
    kanji_dict: dict[str, KanjiEntry],
) -> dict:
    """
    Generate JSON structure for HTML visualization.
    """
    # Group by stroke count
    by_strokes: dict[str, list[dict]] = defaultdict(list)
    entries_list: list[dict] = []

    for entry in kanji_dict.values():
        entry_dict = {
            "char": entry.normalized,
            "original": entry.original,
            "stroke_count": entry.stroke_count,
            "popularity": entry.popularity,
            "is_grapheme": entry.is_grapheme,
            "chise_status": entry.chise_status,
            "kanjivg_status": entry.kanjivg_status,
            "decomp_source": entry.decomp_source,
            "grapheme_id": entry.grapheme_id,
        }
        entries_list.append(entry_dict)
        by_strokes[str(entry.stroke_count)].append(entry_dict)

    # Sort each stroke group by popularity descending
    for stroke_count in by_strokes:
        by_strokes[stroke_count].sort(key=lambda e: e["popularity"], reverse=True)

    # Calculate stats
    total = len(kanji_dict)
    chise_any = sum(1 for e in kanji_dict.values() if e.chise_status != "none")
    kvg_any = sum(1 for e in kanji_dict.values() if e.kanjivg_status != "none")
    from_chise = sum(1 for e in kanji_dict.values() if e.decomp_source == "chise")
    from_chise_atomic = sum(1 for e in kanji_dict.values() if e.decomp_source == "chise-atomic")
    from_kanjivg = sum(1 for e in kanji_dict.values() if e.decomp_source == "kanjivg")
    from_kanjivg_atomic = sum(1 for e in kanji_dict.values() if e.decomp_source == "kanjivg-atomic")
    graphemes = sum(1 for e in kanji_dict.values() if e.is_grapheme)

    return {
        "metadata": {
            "generated": datetime.now(timezone.utc).isoformat(),
            "total_kanji": total,
            "in_chise": chise_any,
            "in_kanjivg": kvg_any,
            "from_chise": from_chise,
            "from_chise_atomic": from_chise_atomic,
            "from_kanjivg": from_kanjivg,
            "from_kanjivg_atomic": from_kanjivg_atomic,
            "graphemes": graphemes,
        },
        "by_stroke_count": dict(by_strokes),
        "entries": entries_list,
    }


def write_json_output(data: dict, output_path: Path) -> None:
    """Write JSON data to file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  Written to: {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Analyze kanji component popularity")
    parser.add_argument("--dry-run", action="store_true", help="Parse data but don't write output files")
    parser.add_argument("--skip-db", action="store_true", help="Skip Turso DB lookup (treat all as non-graphemes)")
    args = parser.parse_args()

    print("Kanji Component Popularity Analyzer")
    print("=" * 40)
    print("Using CHISE IDS (primary) + KanjiVG (fallback)")

    # Step 1: Load CHISE IDS data
    print("\n1. Loading CHISE IDS data...")
    chise_ids = load_chise_ids()  # Uses default path from component_analysis
    print(f"  Found {len(chise_ids)} characters with CHISE IDS data")

    # Step 2: Load KanjiVG index
    print("\n2. Loading KanjiVG index...")
    kanjivg_chars = load_kanjivg_index()  # Uses default path from component_analysis
    print(f"  Found {len(kanjivg_chars)} characters with KanjiVG data")

    # Step 3: Load graphemes from Turso
    print("\n3. Loading graphemes from Turso...")
    if args.skip_db:
        print("  Skipped (--skip-db)")
        grapheme_primaries: dict[str, str] = {}
        variant_to_canonical: dict[str, str] = {}
        variant_to_symbol: dict[str, str] = {}
        grapheme_id_to_doc: dict[str, dict] = {}
    else:
        conn = connect_db()
        grapheme_primaries, variant_to_canonical, variant_to_symbol, grapheme_id_to_doc = load_graphemes_from_turso(conn)
        print(f"  Found {len(grapheme_primaries)} primary graphemes")
        print(f"  Found {len(variant_to_canonical)} variants")
        print(f"  Built {len(variant_to_symbol)} variant->symbol mappings")

    # Create full normalizer that includes grapheme variants
    normalizer = make_grapheme_normalizer(variant_to_symbol)

    # Step 4: Parse kanjidic2.xml
    print("\n4. Parsing kanjidic2.xml...")
    kanjidic_entries = parse_kanjidic()
    print(f"  Found {len(kanjidic_entries)} kanji entries")

    # Step 5: Build memoization dict (First Pass)
    print("\n5. Building memoization dict (First Pass)...")
    kanji_dict = build_memoization_dict(
        kanjidic_entries,
        grapheme_primaries,
        variant_to_canonical,
        chise_ids,
        kanjivg_chars,
        normalizer,
    )
    print(f"  Created {len(kanji_dict)} unique normalized entries")

    # Show source breakdown
    from_chise = sum(1 for e in kanji_dict.values() if e.decomp_source == "chise")
    from_chise_atomic = sum(1 for e in kanji_dict.values() if e.decomp_source == "chise-atomic")
    from_kanjivg = sum(1 for e in kanji_dict.values() if e.decomp_source == "kanjivg")
    from_kanjivg_atomic = sum(1 for e in kanji_dict.values() if e.decomp_source == "kanjivg-atomic")
    no_decomp = sum(1 for e in kanji_dict.values() if e.decomp_source == "none")
    print(f"  From CHISE: {from_chise} decomposed, {from_chise_atomic} atomic")
    print(f"  From KanjiVG: {from_kanjivg} decomposed, {from_kanjivg_atomic} atomic")
    print(f"  None (not in either): {no_decomp}")

    # Step 6: Calculate popularity (Second Pass)
    print("\n6. Calculating popularity (Second Pass - expanded search)...")
    calculate_popularity(
        kanji_dict,
        grapheme_primaries,
        variant_to_canonical,
        grapheme_id_to_doc,
        chise_ids,
        kanjivg_chars,
        normalizer,
    )

    # Step 7: Output
    print("\n7. Writing output...")
    if args.dry_run:
        print("  Dry run - skipping file writes")
    else:
        write_text_report(kanji_dict, OUTPUT_TXT)
        json_data = generate_json_output(kanji_dict)
        write_json_output(json_data, OUTPUT_JSON)
        write_candidates_report(kanji_dict, OUTPUT_CANDIDATES)
        write_grapheme_popularity_report(kanji_dict, OUTPUT_GRAPHEME_POP)

    # Summary stats
    total = len(kanji_dict)
    graphemes = sum(1 for e in kanji_dict.values() if e.is_grapheme)
    top_popular = sorted(
        [e for e in kanji_dict.values() if e.popularity > 0],
        key=lambda e: e.popularity,
        reverse=True
    )[:10]

    print("\n" + "=" * 40)
    print("Summary:")
    print(f"  Total unique normalized kanji: {total}")
    print(f"  Sources: chise={from_chise}, chise-atomic={from_chise_atomic}, kanjivg={from_kanjivg}, kanjivg-atomic={from_kanjivg_atomic}, none={no_decomp}")
    print(f"  Identified as graphemes: {graphemes}")
    print(f"\nTop 10 most popular components:")
    for entry in top_popular:
        # Show "other" library status
        if entry.decomp_source.startswith("chise"):
            other = f"(kvg: {entry.kanjivg_status})"
        elif entry.decomp_source.startswith("kanjivg"):
            other = f"(chise: {entry.chise_status})"
        else:
            other = ""
        print(f"  {entry.normalized}  pop: {entry.popularity:>4}  grapheme: {'Y' if entry.is_grapheme else 'N'}  src: {entry.decomp_source:<13} {other}")

    print("\nDone.")


if __name__ == "__main__":
    main()
