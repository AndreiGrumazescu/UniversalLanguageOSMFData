#!/usr/bin/env python3
"""
jmdict.py

Parse JMdict_e.xml to extract vocabulary entries.
Uses SAX parsing for memory efficiency (the file is ~60MB).
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from xml.sax import ContentHandler, parse as sax_parse
from xml.sax.xmlreader import AttributesImpl

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import JMDICT_PATH


@dataclass
class JMdictSense:
    """A single sense (meaning group) from a JMdict entry."""
    pos: list[str] = field(default_factory=list)
    glosses: list[str] = field(default_factory=list)


@dataclass
class JMdictEntry:
    """A parsed entry from JMdict_e.xml."""
    ent_seq: str = ""
    kanji_elements: list[str] = field(default_factory=list)
    reading_elements: list[str] = field(default_factory=list)
    senses: list[JMdictSense] = field(default_factory=list)

    @property
    def japanese(self) -> str:
        """Primary written form (first kanji element, or first reading if no kanji)."""
        if self.kanji_elements:
            return self.kanji_elements[0]
        return self.reading_elements[0] if self.reading_elements else ""

    @property
    def kana(self) -> str:
        """Primary kana reading."""
        return self.reading_elements[0] if self.reading_elements else ""

    @property
    def primary_pos(self) -> Optional[str]:
        """Part of speech from the first sense."""
        for sense in self.senses:
            if sense.pos:
                return sense.pos[0]
        return None


class JMdictHandler(ContentHandler):
    """
    SAX handler for parsing JMdict_e.xml.

    Extracts entries with kanji elements, reading elements, and senses
    (glosses + parts of speech).
    """

    def __init__(self):
        super().__init__()
        self.entries: list[JMdictEntry] = []
        self.current: Optional[JMdictEntry] = None
        self.current_sense: Optional[JMdictSense] = None
        self.content = ""

        # Element tracking
        self.in_entry = False
        self.in_ent_seq = False
        self.in_k_ele = False
        self.in_keb = False
        self.in_r_ele = False
        self.in_reb = False
        self.in_sense = False
        self.in_pos = False
        self.in_gloss = False
        self.skip_gloss = False

    def startElement(self, name: str, attrs: AttributesImpl):
        self.content = ""

        if name == "entry":
            self.in_entry = True
            self.current = JMdictEntry()

        elif name == "ent_seq" and self.in_entry:
            self.in_ent_seq = True

        elif name == "k_ele" and self.in_entry:
            self.in_k_ele = True

        elif name == "keb" and self.in_k_ele:
            self.in_keb = True

        elif name == "r_ele" and self.in_entry:
            self.in_r_ele = True

        elif name == "reb" and self.in_r_ele:
            self.in_reb = True

        elif name == "sense" and self.in_entry:
            self.in_sense = True
            self.current_sense = JMdictSense()

        elif name == "pos" and self.in_sense:
            self.in_pos = True

        elif name == "gloss" and self.in_sense:
            # Only include English glosses (no xml:lang attribute or xml:lang="eng")
            lang = attrs.get("xml:lang")
            if lang is not None and lang != "eng":
                self.skip_gloss = True
            else:
                self.in_gloss = True
                self.skip_gloss = False

    def endElement(self, name: str):
        if name == "entry":
            if self.current and self.current.ent_seq:
                self.entries.append(self.current)
            self.current = None
            self.in_entry = False

        elif name == "ent_seq":
            if self.in_ent_seq and self.current:
                self.current.ent_seq = self.content.strip()
            self.in_ent_seq = False

        elif name == "k_ele":
            self.in_k_ele = False

        elif name == "keb":
            if self.in_keb and self.current:
                text = self.content.strip()
                if text:
                    self.current.kanji_elements.append(text)
            self.in_keb = False

        elif name == "r_ele":
            self.in_r_ele = False

        elif name == "reb":
            if self.in_reb and self.current:
                text = self.content.strip()
                if text:
                    self.current.reading_elements.append(text)
            self.in_reb = False

        elif name == "sense":
            if self.in_sense and self.current and self.current_sense:
                self.current.senses.append(self.current_sense)
            self.current_sense = None
            self.in_sense = False

        elif name == "pos":
            if self.in_pos and self.current_sense:
                text = self.content.strip()
                if text:
                    self.current_sense.pos.append(text)
            self.in_pos = False

        elif name == "gloss":
            if self.in_gloss and self.current_sense:
                text = self.content.strip()
                if text:
                    self.current_sense.glosses.append(text)
            self.in_gloss = False
            self.skip_gloss = False

    def characters(self, content: str):
        self.content += content


def parse_jmdict(path: Path = JMDICT_PATH) -> list[JMdictEntry]:
    """
    Parse JMdict_e.xml and extract all entries.

    Args:
        path: Path to JMdict_e.xml file

    Returns:
        List of JMdictEntry objects
    """
    handler = JMdictHandler()
    sax_parse(str(path), handler)
    return handler.entries


def parse_jmdict_as_dict(path: Path = JMDICT_PATH) -> dict[str, JMdictEntry]:
    """
    Parse JMdict_e.xml and return as a dictionary keyed by ent_seq.

    Args:
        path: Path to JMdict_e.xml file

    Returns:
        Dict mapping ent_seq -> JMdictEntry
    """
    entries = parse_jmdict(path)
    return {e.ent_seq: e for e in entries}


def build_word_lookup(entries: list[JMdictEntry]) -> dict[tuple[str, str], JMdictEntry]:
    """
    Build a lookup from (japanese_form, kana_reading) to JMdict entry.

    For entries with multiple kanji forms, creates a mapping for each form.
    For kana-only entries, uses (reading, reading) as the key.

    Args:
        entries: List of JMdictEntry objects

    Returns:
        Dict mapping (japanese, kana) -> JMdictEntry
    """
    lookup: dict[tuple[str, str], JMdictEntry] = {}

    for entry in entries:
        if entry.kanji_elements:
            for kanji in entry.kanji_elements:
                for reading in entry.reading_elements:
                    key = (kanji, reading)
                    if key not in lookup:
                        lookup[key] = entry
        else:
            # Kana-only entry
            for reading in entry.reading_elements:
                key = (reading, reading)
                if key not in lookup:
                    lookup[key] = entry

    return lookup


if __name__ == "__main__":
    print(f"Parsing {JMDICT_PATH}...")
    entries = parse_jmdict()
    print(f"Found {len(entries)} total entries")

    with_kanji = [e for e in entries if e.kanji_elements]
    kana_only = [e for e in entries if not e.kanji_elements]
    print(f"  With kanji: {len(with_kanji)}")
    print(f"  Kana-only: {len(kana_only)}")

    multi_sense = [e for e in entries if len(e.senses) > 1]
    print(f"  With multiple senses: {len(multi_sense)}")

    # Show some examples
    print("\nExample entries:")
    for e in entries[:5]:
        print(f"  [{e.ent_seq}] {e.japanese} ({e.kana}): "
              f"senses={len(e.senses)}, pos={e.primary_pos}")
        for i, s in enumerate(e.senses[:3]):
            print(f"    sense {i}: {', '.join(s.glosses[:3])}")
