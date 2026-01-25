#!/usr/bin/env python3
"""
grapheme_io.py

Load and save grapheme-related OSMF documents.
Consolidates grapheme loading logic used across multiple scripts.
"""

import json
from collections import defaultdict
from pathlib import Path
from typing import Optional

from .paths import GRAPHEME_DOCS, DEPENDENCY_DOCS, VARIANT_GROUP_DOCS


# ---------------------------------------------------------------------------
# Grapheme Loading
# ---------------------------------------------------------------------------

def load_graphemes(docs_dir: Path = GRAPHEME_DOCS) -> dict[str, dict]:
    """
    Load all grapheme documents.

    Args:
        docs_dir: Directory containing grapheme JSON files

    Returns:
        Dict mapping $id -> document
    """
    graphemes: dict[str, dict] = {}

    for json_file in docs_dir.glob("*.json"):
        with open(json_file, "r", encoding="utf-8") as f:
            doc = json.load(f)
            graphemes[doc["$id"]] = doc

    return graphemes


def load_graphemes_with_mappings(
    docs_dir: Path = GRAPHEME_DOCS
) -> tuple[dict[str, dict], dict[str, str], dict[str, str]]:
    """
    Load all grapheme documents with symbol mappings.

    Args:
        docs_dir: Directory containing grapheme JSON files

    Returns:
        Tuple of:
        - graphemes: dict mapping $id -> document
        - symbol_to_id: dict mapping primary symbol -> $id
        - variant_to_id: dict mapping variant symbol -> canonical $id
    """
    graphemes: dict[str, dict] = {}
    symbol_to_id: dict[str, str] = {}
    variant_to_id: dict[str, str] = {}

    for json_file in docs_dir.glob("*.json"):
        with open(json_file, "r", encoding="utf-8") as f:
            doc = json.load(f)
            gid = doc["$id"]
            graphemes[gid] = doc

            # Map primary symbol
            symbol = doc.get("symbol")
            if symbol:
                symbol_to_id[symbol] = gid

            # Map variants
            for variant in doc.get("variants", []):
                variant_symbol = variant.get("symbol")
                if variant_symbol:
                    variant_to_id[variant_symbol] = gid

    return graphemes, symbol_to_id, variant_to_id


def load_graphemes_sorted(
    docs_dir: Path = GRAPHEME_DOCS,
    sort_key: Optional[callable] = None
) -> list[dict]:
    """
    Load all grapheme documents as a sorted list.

    Args:
        docs_dir: Directory containing grapheme JSON files
        sort_key: Optional sort key function. Defaults to (strokeCount, unicode).

    Returns:
        List of grapheme documents, sorted
    """
    docs = []

    for filepath in docs_dir.glob("*.json"):
        with open(filepath, "r", encoding="utf-8") as f:
            doc = json.load(f)
            docs.append(doc)

    if sort_key is None:
        sort_key = lambda d: (d.get("strokeCount") or 999, d.get("unicode", ""))

    docs.sort(key=sort_key)
    return docs


# ---------------------------------------------------------------------------
# Dependency Loading
# ---------------------------------------------------------------------------

def load_dependencies(
    docs_dir: Path = DEPENDENCY_DOCS
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """
    Load grapheme dependency documents.

    Args:
        docs_dir: Directory containing dependency JSON files

    Returns:
        Tuple of:
        - deps: dict mapping parent_id -> [component_ids]
        - reverse_deps: dict mapping component_id -> [parent_ids]
    """
    deps: dict[str, list[str]] = {}
    reverse_deps: dict[str, list[str]] = defaultdict(list)

    for json_file in docs_dir.glob("*.json"):
        with open(json_file, "r", encoding="utf-8") as f:
            doc = json.load(f)
            parent_id = doc["connectors"]["parent"]["$id"]

            # Extract unique components while preserving order
            components = []
            seen = set()
            for item in doc.get("many", []):
                cid = item["connectors"]["component"]["$id"]
                if cid not in seen:
                    seen.add(cid)
                    components.append(cid)

            deps[parent_id] = components

            for cid in components:
                reverse_deps[cid].append(parent_id)

    return deps, dict(reverse_deps)


# ---------------------------------------------------------------------------
# Variant Group Loading
# ---------------------------------------------------------------------------

def load_variant_groups(
    docs_dir: Path = VARIANT_GROUP_DOCS
) -> dict[str, dict]:
    """
    Load all variant group documents.

    Args:
        docs_dir: Directory containing variant group JSON files

    Returns:
        Dict mapping $id -> document
    """
    groups: dict[str, dict] = {}

    for json_file in docs_dir.glob("*.json"):
        with open(json_file, "r", encoding="utf-8") as f:
            doc = json.load(f)
            groups[doc["$id"]] = doc

    return groups


# ---------------------------------------------------------------------------
# JSON Document Writing
# ---------------------------------------------------------------------------

def write_json_document(doc: dict, filepath: Path) -> bool:
    """
    Write a JSON document with standard formatting.

    Uses ensure_ascii=False, indent=2, and adds trailing newline.

    Args:
        doc: The document to write
        filepath: Path to write to

    Returns:
        True if file was created or content changed, False if unchanged
    """
    # Check if content changed
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                existing = json.load(f)
                if existing == doc:
                    return False  # No change
            except json.JSONDecodeError:
                pass  # File is corrupted, overwrite it

    # Ensure parent directory exists
    filepath.parent.mkdir(parents=True, exist_ok=True)

    # Write the document
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")

    return True


def delete_json_document(filepath: Path) -> bool:
    """
    Delete a JSON document if it exists.

    Args:
        filepath: Path to delete

    Returns:
        True if file was deleted, False if it didn't exist
    """
    if filepath.exists():
        filepath.unlink()
        return True
    return False


# ---------------------------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------------------------

def build_variant_to_symbol_mapping(
    graphemes: dict[str, dict],
    symbol_to_id: dict[str, str],
    variant_to_id: dict[str, str]
) -> dict[str, str]:
    """
    Build a mapping from variant symbols to their canonical symbols.

    Args:
        graphemes: Dict mapping $id -> document
        symbol_to_id: Dict mapping symbol -> $id
        variant_to_id: Dict mapping variant symbol -> canonical $id

    Returns:
        Dict mapping variant symbol -> canonical symbol
    """
    # Build reverse mapping: grapheme ID -> canonical symbol
    id_to_symbol: dict[str, str] = {}
    for symbol, gid in symbol_to_id.items():
        id_to_symbol[gid] = symbol

    # Build variant symbol -> canonical symbol mapping
    variant_to_symbol: dict[str, str] = {}
    for variant_sym, gid in variant_to_id.items():
        canonical_sym = id_to_symbol.get(gid)
        if canonical_sym:
            variant_to_symbol[variant_sym] = canonical_sym

    return variant_to_symbol
