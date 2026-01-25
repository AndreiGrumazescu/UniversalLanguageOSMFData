#!/usr/bin/env python3
"""
kanjidic.py

Parse kanjidic2.xml to extract kanji entries with stroke counts.
Consolidates parsing logic used by multiple scripts.
"""

import sys
from pathlib import Path
from typing import Optional
from xml.sax import ContentHandler, parse as sax_parse

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import KANJIDIC_PATH


class KanjidictHandler(ContentHandler):
    """
    SAX handler for parsing kanjidic2.xml.

    Extracts kanji characters and their stroke counts.
    """

    def __init__(self):
        super().__init__()
        self.entries: list[tuple[str, int]] = []  # (kanji, stroke_count)
        self.in_character = False
        self.in_literal = False
        self.in_misc = False
        self.in_stroke_count = False
        self.current_literal = ""
        self.current_stroke_count: Optional[int] = None
        self.content = ""

    def startElement(self, name, attrs):
        self.content = ""
        if name == "character":
            self.in_character = True
            self.current_literal = ""
            self.current_stroke_count = None
        elif name == "literal" and self.in_character:
            self.in_literal = True
        elif name == "misc" and self.in_character:
            self.in_misc = True
        elif name == "stroke_count" and self.in_misc:
            self.in_stroke_count = True

    def endElement(self, name):
        if name == "character":
            if self.current_literal and self.current_stroke_count is not None:
                self.entries.append((self.current_literal, self.current_stroke_count))
            self.in_character = False
        elif name == "literal":
            if self.in_literal:
                self.current_literal = self.content.strip()
            self.in_literal = False
        elif name == "misc":
            self.in_misc = False
        elif name == "stroke_count":
            if self.in_stroke_count and self.current_stroke_count is None:
                # Only take the first stroke_count (primary count)
                try:
                    self.current_stroke_count = int(self.content.strip())
                except ValueError:
                    pass
            self.in_stroke_count = False

    def characters(self, content):
        self.content += content


def parse_kanjidic(path: Path = KANJIDIC_PATH) -> list[tuple[str, int]]:
    """
    Parse kanjidic2.xml and extract all kanji with stroke counts.

    Args:
        path: Path to kanjidic2.xml file

    Returns:
        List of (kanji_char, stroke_count) tuples
    """
    handler = KanjidictHandler()
    sax_parse(str(path), handler)
    return handler.entries


def parse_kanjidic_as_dict(path: Path = KANJIDIC_PATH) -> dict[str, int]:
    """
    Parse kanjidic2.xml and return as a dictionary.

    Args:
        path: Path to kanjidic2.xml file

    Returns:
        Dict mapping kanji_char -> stroke_count
    """
    entries = parse_kanjidic(path)
    return {kanji: strokes for kanji, strokes in entries}


if __name__ == "__main__":
    # Test the parser
    print(f"Parsing {KANJIDIC_PATH}...")
    entries = parse_kanjidic()
    print(f"Found {len(entries)} kanji entries")

    # Show some examples
    print("\nFirst 10 entries:")
    for kanji, strokes in entries[:10]:
        print(f"  {kanji}: {strokes} strokes")

    print("\nLast 10 entries:")
    for kanji, strokes in entries[-10:]:
        print(f"  {kanji}: {strokes} strokes")
