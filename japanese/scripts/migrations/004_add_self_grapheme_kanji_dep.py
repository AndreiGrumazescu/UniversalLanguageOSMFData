#!/usr/bin/env python3
"""
004_add_self_grapheme_kanji_dep.py

Ensure every kanji whose primary symbol matches a grapheme's primary symbol
has the matching grapheme listed as a component in its kanji-grapheme-
dependency document. Covers two cases:

  (A) The kanji has NO kanji-grapheme-dependency document at all. Create a
      new document whose sole component is the self-grapheme.
  (B) The kanji has a dependency document, but its `many[].component.$id`
      does not include the self-grapheme. Prepend the self-grapheme to the
      `many` list, preserving existing components and their order.

Idempotent: re-running is a no-op once every shared-symbol pair satisfies
the invariant. Uses lib.grapheme_io.write_json_document, which skips writes
when content is unchanged.

This migration does not transform existing documents in place via the
standard `_runner.py` (which walks one target directory and transforms each
file one-to-one). It also creates new documents for case (A), so it runs its
own loop while preserving the log format used by `_runner.py`.
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.grapheme_io import load_graphemes, write_json_document
from lib.paths import (
    KANJI_DOCS,
    KANJI_GRAPHEME_DEP_DIR,
    KANJI_GRAPHEME_DEP_DOCS,
    MIGRATION_LOGS_DIR,
)


NUMBER = 4
SLUG = "add_self_grapheme_kanji_dep"
GOAL = (
    "For every kanji whose primary symbol matches a grapheme's primary symbol, "
    "ensure the kanji-grapheme-dependency document includes that grapheme as "
    "a component. Creates missing dependency docs; prepends the self-grapheme "
    "to existing docs that omit it."
)
TARGET_DIR = KANJI_GRAPHEME_DEP_DOCS
SCHEMA_PATH = KANJI_GRAPHEME_DEP_DIR / "japanese-kanji-grapheme-dependency.schema.json"


def _load_kanji() -> dict[str, dict]:
    """Load all kanji documents keyed by $id."""
    out: dict[str, dict] = {}
    for json_file in KANJI_DOCS.glob("*.json"):
        with open(json_file, "r", encoding="utf-8") as f:
            doc = json.load(f)
            out[doc["$id"]] = doc
    return out


def _load_dep_files() -> dict[str, Path]:
    """Map parent kanji $id -> filepath for every existing dep doc."""
    out: dict[str, Path] = {}
    for json_file in KANJI_GRAPHEME_DEP_DOCS.glob("*.json"):
        with open(json_file, "r", encoding="utf-8") as f:
            doc = json.load(f)
        parent_id = doc["connectors"]["parent"]["$id"]
        out[parent_id] = json_file
    return out


def _dep_path_for_kanji(kanji_id: str) -> Path:
    """Return the canonical file path for a kanji's dep doc."""
    # kanji:U+XXXX -> kanji-grapheme-dep:U+XXXX
    unicode_id = kanji_id.split(":", 1)[1]
    return KANJI_GRAPHEME_DEP_DOCS / f"kanji-grapheme-dep:{unicode_id}.json"


def _new_dep_doc(kanji_id: str, grapheme_id: str) -> dict:
    """Build a fresh dep doc with a single self-grapheme component."""
    unicode_id = kanji_id.split(":", 1)[1]
    return {
        "$id": f"kanji-grapheme-dep:{unicode_id}",
        "connectors": {"parent": {"$id": kanji_id}},
        "many": [
            {"connectors": {"component": {"$id": grapheme_id}}},
        ],
    }


def _prepend_self_component(doc: dict, grapheme_id: str) -> dict:
    """
    Return a new doc with the self-grapheme prepended to `many`. Caller must
    guarantee `grapheme_id` is not already present; this function does not
    dedupe beyond a defensive check.
    """
    existing = list(doc.get("many", []))
    for item in existing:
        cid = item.get("connectors", {}).get("component", {}).get("$id")
        if cid == grapheme_id:
            # Defensive: already present, no change.
            return doc
    new_doc = dict(doc)
    new_doc["many"] = [
        {"connectors": {"component": {"$id": grapheme_id}}},
        *existing,
    ]
    return new_doc


def _log_filename(number: int, slug: str) -> str:
    return f"{number:03d}_{slug}_migration_log.txt"


def _write_log_header(log_path: Path) -> None:
    content = (
        f"Migration {NUMBER:03d}: {SLUG}\n"
        f"Goal: {GOAL}\n"
        f"Target: {TARGET_DIR}\n"
        f"Schema: {SCHEMA_PATH}\n"
        f"\n"
        f"Runs:\n"
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(content, encoding="utf-8")


def _append_log_run(
    log_path: Path,
    scanned: int,
    created: int,
    updated: int,
    errored: int,
    elapsed: float,
) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = (
        f"  {timestamp}  scanned={scanned} created={created} "
        f"updated={updated} errored={errored} elapsed={elapsed:.1f}s\n"
    )
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=f"Migration {NUMBER:03d}: {SLUG}"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing files or log",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process at most N shared-symbol pairs (for testing)",
    )
    args = parser.parse_args()

    print(f"Migration {NUMBER:03d}: {SLUG}")
    print("=" * 60)
    print(f"  Goal:   {GOAL}")
    print(f"  Target: {TARGET_DIR}")
    print(f"  Schema: {SCHEMA_PATH}")
    print("=" * 60)

    if not SCHEMA_PATH.exists():
        print(f"\nERROR: schema file not found: {SCHEMA_PATH}")
        sys.exit(1)
    if not TARGET_DIR.exists():
        print(f"\nERROR: target directory not found: {TARGET_DIR}")
        sys.exit(1)

    print("\nLoading graphemes, kanji, and existing dep docs…")
    graphemes = load_graphemes()
    kanji = _load_kanji()
    dep_files = _load_dep_files()
    print(
        f"  graphemes={len(graphemes)}  kanji={len(kanji)}  "
        f"dep_docs={len(dep_files)}"
    )

    # Build symbol -> kanji lookup (primary symbol only)
    kanji_by_symbol: dict[str, dict] = {}
    for doc in kanji.values():
        symbol = doc.get("symbol")
        if symbol:
            kanji_by_symbol[symbol] = doc

    # Enumerate shared-symbol pairs (grapheme, kanji)
    shared: list[tuple[dict, dict]] = []
    for g in graphemes.values():
        symbol = g.get("symbol")
        if not symbol:
            continue
        k = kanji_by_symbol.get(symbol)
        if k is not None:
            shared.append((g, k))

    # Deterministic order: strokeCount, then unicode
    shared.sort(
        key=lambda pair: (pair[0].get("strokeCount") or 999, pair[0].get("unicode", ""))
    )

    if args.limit is not None:
        shared = shared[: args.limit]

    print(f"\nShared-symbol pairs: {len(shared)}")

    start = time.time()
    scanned = created = updated = errored = 0
    errors: list[tuple[str, str]] = []

    for g, k in shared:
        scanned += 1
        kanji_id = k.get("$id", "")
        grapheme_id = g.get("$id", "")

        try:
            existing_path = dep_files.get(kanji_id)

            if existing_path is None:
                # Case (A): create a new dep doc
                new_doc = _new_dep_doc(kanji_id, grapheme_id)
                target_path = _dep_path_for_kanji(kanji_id)
                if args.dry_run:
                    created += 1
                else:
                    if write_json_document(new_doc, target_path):
                        created += 1
            else:
                # Case (B) or already-satisfied: load existing, inspect
                with open(existing_path, "r", encoding="utf-8") as f:
                    original = json.load(f)

                components = [
                    item.get("connectors", {}).get("component", {}).get("$id")
                    for item in original.get("many", [])
                ]
                if grapheme_id in components:
                    continue  # already satisfied

                new_doc = _prepend_self_component(original, grapheme_id)
                if args.dry_run:
                    if new_doc != original:
                        updated += 1
                else:
                    if write_json_document(new_doc, existing_path):
                        updated += 1
        except Exception as e:
            errored += 1
            errors.append((kanji_id, f"{type(e).__name__}: {e}"))

    elapsed = time.time() - start

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"  Scanned: {scanned}")
    print(f"  Created: {created}{'  (dry-run)' if args.dry_run else ''}")
    print(f"  Updated: {updated}{'  (dry-run)' if args.dry_run else ''}")
    print(f"  Errored: {errored}")
    print(f"  Elapsed: {elapsed:.1f}s")

    if errors:
        print("\nErrors:")
        for name, msg in errors[:20]:
            print(f"  {name}: {msg}")
        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more")

    if args.dry_run:
        print("\nDRY RUN — no log written.")
        return

    log_path = MIGRATION_LOGS_DIR / _log_filename(NUMBER, SLUG)
    if not log_path.exists():
        _write_log_header(log_path)
    _append_log_run(log_path, scanned, created, updated, errored, elapsed)
    print(f"\nLog: {log_path}")


if __name__ == "__main__":
    main()
