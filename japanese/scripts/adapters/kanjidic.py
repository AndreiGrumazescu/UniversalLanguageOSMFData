#!/usr/bin/env python3
"""
kanjidic.py

Parse kanjidic2.xml to extract kanji entries.
Consolidates parsing logic used by multiple scripts.
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from xml.sax import ContentHandler, parse as sax_parse
from xml.sax.xmlreader import AttributesImpl

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import KANJIDIC_PATH


@dataclass
class KanjiEntry:
    """A parsed kanji entry from kanjidic2.xml."""
    literal: str = ""
    stroke_count: Optional[int] = None
    grade: Optional[int] = None
    meanings: list[str] = field(default_factory=list)
    onyomi: list[str] = field(default_factory=list)
    kunyomi: list[str] = field(default_factory=list)


class KanjidictFullHandler(ContentHandler):
    """
    SAX handler for parsing kanjidic2.xml.

    Extracts kanji characters with stroke counts, grade, meanings, and readings.
    """

    def __init__(self):
        super().__init__()
        self.entries: list[KanjiEntry] = []
        self.current: Optional[KanjiEntry] = None
        self.content = ""

        # Element tracking
        self.in_character = False
        self.in_literal = False
        self.in_misc = False
        self.in_stroke_count = False
        self.in_grade = False
        self.in_reading_meaning = False
        self.in_rmgroup = False
        self.in_reading = False
        self.in_meaning = False
        self.got_stroke_count = False

        # Attribute tracking for current element
        self.current_reading_type: Optional[str] = None
        self.current_meaning_lang: Optional[str] = None

    def startElement(self, name: str, attrs: AttributesImpl):
        self.content = ""

        if name == "character":
            self.in_character = True
            self.current = KanjiEntry()
            self.got_stroke_count = False

        elif name == "literal" and self.in_character:
            self.in_literal = True

        elif name == "misc" and self.in_character:
            self.in_misc = True

        elif name == "stroke_count" and self.in_misc:
            self.in_stroke_count = True

        elif name == "grade" and self.in_misc:
            self.in_grade = True

        elif name == "reading_meaning" and self.in_character:
            self.in_reading_meaning = True

        elif name == "rmgroup" and self.in_reading_meaning:
            self.in_rmgroup = True

        elif name == "reading" and self.in_rmgroup:
            self.in_reading = True
            self.current_reading_type = attrs.get("r_type")

        elif name == "meaning" and self.in_rmgroup:
            self.in_meaning = True
            self.current_meaning_lang = attrs.get("m_lang")

    def endElement(self, name: str):
        if name == "character":
            if self.current and self.current.literal:
                self.entries.append(self.current)
            self.current = None
            self.in_character = False

        elif name == "literal":
            if self.in_literal and self.current:
                self.current.literal = self.content.strip()
            self.in_literal = False

        elif name == "misc":
            self.in_misc = False

        elif name == "stroke_count":
            if self.in_stroke_count and self.current and not self.got_stroke_count:
                # Only take the first stroke_count (primary count)
                try:
                    self.current.stroke_count = int(self.content.strip())
                    self.got_stroke_count = True
                except ValueError:
                    pass
            self.in_stroke_count = False

        elif name == "grade":
            if self.in_grade and self.current:
                try:
                    self.current.grade = int(self.content.strip())
                except ValueError:
                    pass
            self.in_grade = False

        elif name == "reading_meaning":
            self.in_reading_meaning = False

        elif name == "rmgroup":
            self.in_rmgroup = False

        elif name == "reading":
            if self.in_reading and self.current:
                text = self.content.strip()
                if text:
                    if self.current_reading_type == "ja_on":
                        self.current.onyomi.append(text)
                    elif self.current_reading_type == "ja_kun":
                        self.current.kunyomi.append(text)
            self.in_reading = False
            self.current_reading_type = None

        elif name == "meaning":
            if self.in_meaning and self.current:
                text = self.content.strip()
                # Only English meanings (no m_lang attribute)
                if text and self.current_meaning_lang is None:
                    self.current.meanings.append(text)
            self.in_meaning = False
            self.current_meaning_lang = None

    def characters(self, content: str):
        self.content += content


def parse_kanjidic_full(path: Path = KANJIDIC_PATH) -> list[KanjiEntry]:
    """
    Parse kanjidic2.xml and extract full kanji entries.

    Args:
        path: Path to kanjidic2.xml file

    Returns:
        List of KanjiEntry objects
    """
    handler = KanjidictFullHandler()
    sax_parse(str(path), handler)
    return handler.entries


# ---------------------------------------------------------------------------
# Legacy API (used by grapheme scripts)
# ---------------------------------------------------------------------------

def parse_kanjidic(path: Path = KANJIDIC_PATH) -> list[tuple[str, int]]:
    """
    Parse kanjidic2.xml and extract all kanji with stroke counts.

    Args:
        path: Path to kanjidic2.xml file

    Returns:
        List of (kanji_char, stroke_count) tuples
    """
    handler = KanjidictFullHandler()
    sax_parse(str(path), handler)
    return [
        (e.literal, e.stroke_count)
        for e in handler.entries
        if e.stroke_count is not None
    ]


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
    entries = parse_kanjidic_full()
    print(f"Found {len(entries)} total entries")

    graded = [e for e in entries if e.grade is not None]
    print(f"  With grade (Jouyou + Jinmeiyou): {len(graded)}")

    with_meanings = [e for e in entries if e.meanings]
    print(f"  With meanings: {len(with_meanings)}")

    # Show some examples
    print("\nFirst 5 graded entries:")
    for e in graded[:5]:
        print(f"  {e.literal}: grade={e.grade}, strokes={e.stroke_count}, "
              f"meanings={e.meanings[:3]}, on={e.onyomi[:2]}, kun={e.kunyomi[:2]}")
