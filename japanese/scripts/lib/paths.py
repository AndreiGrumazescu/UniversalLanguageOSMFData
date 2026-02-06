#!/usr/bin/env python3
"""
paths.py

Centralized path configuration for Japanese language scripts.
All scripts should import paths from this module rather than defining them locally.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Base Directories
# ---------------------------------------------------------------------------

LIB_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = LIB_DIR.parent
JAPANESE_ROOT = SCRIPT_DIR.parent
PROJECT_ROOT = JAPANESE_ROOT.parent.parent  # universal-language-new/

# ---------------------------------------------------------------------------
# Data Directories (OSMF Documents)
# ---------------------------------------------------------------------------

DATA_DIR = JAPANESE_ROOT / "data"

# Grapheme data
GRAPHEME_DIR = DATA_DIR / "grapheme"
GRAPHEME_DOCS = GRAPHEME_DIR / "documents"

# Grapheme dependency data
DEPENDENCY_DIR = DATA_DIR / "grapheme-dependency"
DEPENDENCY_DOCS = DEPENDENCY_DIR / "documents"

# Grapheme variant group data
VARIANT_GROUP_DIR = DATA_DIR / "grapheme-variant-group"
VARIANT_GROUP_DOCS = VARIANT_GROUP_DIR / "documents"

# Kanji data
KANJI_DIR = DATA_DIR / "kanji"
KANJI_DOCS = KANJI_DIR / "documents"

# Kanji dependency data (kanji -> kanji)
KANJI_DEP_DIR = DATA_DIR / "kanji-dependency"
KANJI_DEP_DOCS = KANJI_DEP_DIR / "documents"

# Kanji grapheme dependency data (kanji -> grapheme)
KANJI_GRAPHEME_DEP_DIR = DATA_DIR / "kanji-grapheme-dependency"
KANJI_GRAPHEME_DEP_DOCS = KANJI_GRAPHEME_DEP_DIR / "documents"

# ---------------------------------------------------------------------------
# Source Data (External Datasets)
# ---------------------------------------------------------------------------

SOURCE_DIR = SCRIPT_DIR / "source"

# Kanjidic2
KANJIDIC_PATH = SOURCE_DIR / "kanjidic2.xml"

# CHISE IDS
CHISE_IDS_DIR = SOURCE_DIR / "chise-ids"
CHISE_IDS_PATH = CHISE_IDS_DIR / "IDS-UCS-Basic.txt"

# KanjiVG
KANJIVG_DIR = SOURCE_DIR / "kanjivg"
KVG_INDEX_PATH = KANJIVG_DIR / "kvg-index.json"
KVG_KANJI_DIR = KANJIVG_DIR / "kanji"

# Unihan
UNIHAN_DIR = SOURCE_DIR / "unihan"
UNIHAN_IRG_PATH = UNIHAN_DIR / "Unihan_IRGSources.txt"

# ---------------------------------------------------------------------------
# Output Directories
# ---------------------------------------------------------------------------

DOCS_DIR = JAPANESE_ROOT / "docs"
REPORTS_DIR = DOCS_DIR / "reports"

# ---------------------------------------------------------------------------
# Infrastructure (Turso credentials)
# ---------------------------------------------------------------------------

TURSO_ENV_FILE = PROJECT_ROOT / "UL-App" / "infra" / "turso" / ".env"
