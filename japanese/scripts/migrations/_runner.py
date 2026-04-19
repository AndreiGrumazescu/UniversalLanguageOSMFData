#!/usr/bin/env python3
"""
_runner.py

Shared CLI runner for document migrations.

Each migration is a module that declares:
    NUMBER: int
    SLUG: str
    GOAL: str
    TARGET_DIR: Path
    SCHEMA_PATH: Path
    def transform(doc: dict) -> dict

Optional:
    def preflight(schema: dict) -> str | None   # return error message, or None

A migration invokes this runner via:
    if __name__ == "__main__":
        run_cli(sys.modules[__name__])

The runner handles: CLI flags, schema pre-flight, per-file transform + idempotent
write, counters, and migration-log emission.
"""

import argparse
import copy
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.grapheme_io import write_json_document
from lib.paths import MIGRATION_LOGS_DIR


def _log_filename(number: int, slug: str) -> str:
    return f"{number:03d}_{slug}_migration_log.txt"


def _write_log_header(log_path: Path, number: int, slug: str, goal: str,
                      target_dir: Path, schema_path: Path) -> None:
    """Write the fixed header for a new migration log."""
    content = (
        f"Migration {number:03d}: {slug}\n"
        f"Goal: {goal}\n"
        f"Target: {target_dir}\n"
        f"Schema: {schema_path}\n"
        f"\n"
        f"Runs:\n"
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(content, encoding="utf-8")


def _append_log_run(log_path: Path, scanned: int, modified: int,
                    errored: int, elapsed: float) -> None:
    """Append a single run line to the migration log."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = (
        f"  {timestamp}  scanned={scanned} modified={modified} "
        f"errored={errored} elapsed={elapsed:.1f}s\n"
    )
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line)


def run_cli(module: ModuleType) -> None:
    """
    CLI entrypoint for a migration module.

    Args:
        module: The migration module (pass sys.modules[__name__])
    """
    number: int = module.NUMBER
    slug: str = module.SLUG
    goal: str = module.GOAL
    target_dir: Path = module.TARGET_DIR
    schema_path: Path = module.SCHEMA_PATH
    transform = module.transform
    preflight = getattr(module, "preflight", None)

    parser = argparse.ArgumentParser(
        description=f"Migration {number:03d}: {slug}"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would change without writing files or log")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process at most N documents (for testing)")
    args = parser.parse_args()

    print(f"Migration {number:03d}: {slug}")
    print("=" * 60)
    print(f"  Goal:   {goal}")
    print(f"  Target: {target_dir}")
    print(f"  Schema: {schema_path}")
    print("=" * 60)

    # Schema pre-flight
    if not schema_path.exists():
        print(f"\nERROR: schema file not found: {schema_path}")
        sys.exit(1)

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    if preflight is not None:
        err = preflight(schema)
        if err:
            print(f"\nERROR: schema pre-flight failed: {err}")
            print("Update the schema in the same commit as this migration, "
                  "then re-run.")
            sys.exit(1)
        print("\nSchema pre-flight: OK")

    # Walk target directory
    if not target_dir.exists():
        print(f"\nERROR: target directory not found: {target_dir}")
        sys.exit(1)

    files = sorted(target_dir.glob("*.json"))
    if args.limit is not None:
        files = files[: args.limit]
    print(f"\nFound {len(files)} documents")

    # Per-file loop
    start = time.time()
    scanned = modified = errored = 0
    errors: list[tuple[str, str]] = []

    for filepath in files:
        scanned += 1
        try:
            original = json.loads(filepath.read_text(encoding="utf-8"))
            new_doc = transform(copy.deepcopy(original))
        except Exception as e:
            errored += 1
            errors.append((filepath.name, f"{type(e).__name__}: {e}"))
            continue

        if args.dry_run:
            if new_doc != original:
                modified += 1
        else:
            if write_json_document(new_doc, filepath):
                modified += 1

    elapsed = time.time() - start

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"  Scanned:  {scanned}")
    print(f"  Modified: {modified}{'  (dry-run)' if args.dry_run else ''}")
    print(f"  Errored:  {errored}")
    print(f"  Elapsed:  {elapsed:.1f}s")

    if errors:
        print("\nErrors:")
        for name, msg in errors[:20]:
            print(f"  {name}: {msg}")
        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more")

    # Log emission (skipped on dry-run)
    if args.dry_run:
        print("\nDRY RUN — no log written.")
        return

    log_path = MIGRATION_LOGS_DIR / _log_filename(number, slug)
    if not log_path.exists():
        _write_log_header(log_path, number, slug, goal, target_dir, schema_path)
    _append_log_run(log_path, scanned, modified, errored, elapsed)
    print(f"\nLog: {log_path}")
