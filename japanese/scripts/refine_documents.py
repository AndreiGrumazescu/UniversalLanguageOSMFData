#!/usr/bin/env python3
"""
refine_documents.py

AI-powered batch document refinement orchestrator.

Splits a directory of JSON documents into batches, then invokes parallel Claude
Code sub-agents. Each sub-agent receives only:
  - The refinement goal
  - The file paths to process

Features:
  - Parallel execution (--workers N)
  - Retry with exponential backoff on rate-limit (429) or transient errors
  - Persistent progress ledger — tracks completed files across runs so
    interrupted jobs can resume without re-processing finished work
  - --reset-progress to clear the ledger and start fresh

Usage:
    python refine_documents.py <documents_dir> --goal "..." [options]

Examples:
    # Split kanji onyomi into primary/secondary (5 workers, auto-resume)
    python refine_documents.py ../data/kanji/documents \\
        --goal "For each kanji document: if 'onyomi' has more than one reading, \\
                keep the single most common reading in 'onyomi' and move the rest \\
                to 'secondaryOnyomi'." \\
        --batch-size 5 --workers 5

    # Dry run to see what would be processed
    python refine_documents.py ../data/kanji/documents \\
        --goal "..." --dry-run

    # Clear progress and start over
    python refine_documents.py ../data/kanji/documents \\
        --goal "..." --reset-progress
"""

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


# ---------------------------------------------------------------------------
# Progress Ledger
# ---------------------------------------------------------------------------

class ProgressLedger:
    """
    Thread-safe persistent ledger tracking which files have been successfully
    refined. Stored as a JSON file alongside the documents directory.

    File format:
    {
        "completed": ["file1.json", "file2.json", ...]
    }
    """

    def __init__(self, ledger_path: Path):
        self._path = ledger_path
        self._lock = threading.Lock()
        self._completed: set[str] = set()
        self._load()

    def _load(self) -> None:
        """Load existing progress from disk."""
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                self._completed = set(data.get("completed", []))
            except (json.JSONDecodeError, KeyError):
                self._completed = set()

    def _save(self) -> None:
        """Write current progress to disk. Caller must hold _lock."""
        data = {"completed": sorted(self._completed)}
        self._path.write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8"
        )

    def is_done(self, filename: str) -> bool:
        """Check if a file has already been refined."""
        return filename in self._completed

    def mark_done(self, filenames: list[str]) -> None:
        """Mark files as completed and persist immediately."""
        with self._lock:
            self._completed.update(filenames)
            self._save()

    def reset(self) -> None:
        """Clear all progress."""
        with self._lock:
            self._completed.clear()
            if self._path.exists():
                self._path.unlink()

    @property
    def count(self) -> int:
        return len(self._completed)


def default_ledger_path(documents_dir: Path) -> Path:
    """
    Place the ledger file next to the documents directory.
    e.g. data/kanji/documents/ -> data/kanji/.refine-progress.json
    """
    return documents_dir.parent / ".refine-progress.json"


# ---------------------------------------------------------------------------
# Document Discovery & Batching
# ---------------------------------------------------------------------------

def discover_documents(directory: Path, pattern: str = "*.json") -> list[Path]:
    """Find all JSON documents in the given directory."""
    files = sorted(directory.glob(pattern))
    return [f for f in files if f.is_file()]


def batch_files(files: list[Path], batch_size: int) -> list[list[Path]]:
    """Split files into batches of the given size."""
    return [files[i:i + batch_size] for i in range(0, len(files), batch_size)]


# ---------------------------------------------------------------------------
# Prompt Builder
# ---------------------------------------------------------------------------

def build_agent_prompt(goal: str, file_paths: list[Path], schema_path: Path | None) -> str:
    """
    Build a minimal prompt for a sub-agent.

    The prompt contains ONLY:
    - The refinement goal
    - The schema (if provided) for reference
    - The exact file paths to process
    - Instructions to read, modify, and write each file
    """
    files_list = "\n".join(f"- {p}" for p in file_paths)

    schema_section = ""
    if schema_path and schema_path.exists():
        schema_section = f"""
## Schema Reference

The documents conform to the schema at: {schema_path}
Read this schema first to understand the document structure.
"""

    return f"""You are a document refinement agent. Your ONLY task is to apply the refinement goal below to each of the listed JSON files.

## Refinement Goal

{goal}

{schema_section}
## Files to Process

{files_list}

## Instructions

1. Read each file listed above.
2. Apply the refinement goal to each document. Preserve all existing fields — only add or rearrange fields as described in the goal.
3. Write the modified document back to the same path. Use compact pretty-print (2-space indent, no trailing newline after the closing brace).
4. Do NOT modify any files not listed above.
5. Do NOT create any new files.
6. After processing all files, output a brief summary line for each file: the filename and what changed (or "no change needed").
"""


def find_schema(documents_dir: Path) -> Path | None:
    """
    Look for a schema file in the parent directory of the documents folder.

    Convention: documents live in {model}/documents/, schema is {model}/*.schema.json
    """
    parent = documents_dir.parent
    schemas = list(parent.glob("*.schema.json"))
    if len(schemas) == 1:
        return schemas[0]
    return None


# ---------------------------------------------------------------------------
# Thread-safe Logging
# ---------------------------------------------------------------------------

_print_lock = threading.Lock()

def _log(msg: str) -> None:
    """Thread-safe print."""
    with _print_lock:
        print(msg, flush=True)


# ---------------------------------------------------------------------------
# Batch Execution with Retry
# ---------------------------------------------------------------------------

MAX_RETRIES = 3
RETRY_BASE_DELAY = 30  # seconds — 429 backoff starts here


def _is_rate_limit(result: subprocess.CompletedProcess) -> bool:
    """Check if a failed subprocess hit a rate limit."""
    combined = (result.stderr or "") + (result.stdout or "")
    return any(s in combined.lower() for s in ["429", "rate limit", "overloaded", "too many requests"])


def run_batch(
    batch_index: int,
    total_batches: int,
    file_paths: list[Path],
    goal: str,
    schema_path: Path | None,
    model: str,
    max_turns: int,
    ledger: ProgressLedger,
) -> tuple[int, bool, str]:
    """
    Run a single sub-agent batch with retry on transient/rate-limit errors.

    On success, marks files as completed in the ledger.
    Returns (batch_index, success, output_summary).
    """
    prompt = build_agent_prompt(goal, file_paths, schema_path)

    cmd = [
        "claude",
        "-p",
        "--model", model,
        "--dangerously-skip-permissions",
        "--allowedTools", "Read", "Write", "Edit", "Glob",
        "--no-session-persistence",
        prompt,
    ]

    label = f"[Batch {batch_index + 1}/{total_batches}]"
    file_names = [p.name for p in file_paths]
    _log(f"{label} Starting — {len(file_paths)} files: {file_names[0]}...{file_names[-1]}")

    last_error = ""

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout per batch
                cwd=str(file_paths[0].parent),
            )

            if result.returncode == 0:
                # Success — record in ledger
                ledger.mark_done([p.name for p in file_paths])
                output_lines = result.stdout.strip().split("\n")
                summary = "\n".join(output_lines[-min(len(output_lines), 20):])
                _log(f"{label} Done. ({ledger.count} files completed total)")
                return (batch_index, True, summary)

            # Check if rate-limited or overloaded
            if _is_rate_limit(result) and attempt < MAX_RETRIES:
                delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))  # 30s, 60s, 120s
                _log(f"{label} Rate-limited (attempt {attempt}/{MAX_RETRIES}), "
                     f"retrying in {delay}s...")
                time.sleep(delay)
                continue

            # Non-retryable failure
            last_error = (result.stderr.strip() or result.stdout.strip())[:500]
            _log(f"{label} FAILED (exit code {result.returncode}, attempt {attempt})")

            # Still retry non-429 errors once in case of transient issues
            if attempt < MAX_RETRIES:
                delay = 10 * attempt
                _log(f"{label} Retrying in {delay}s...")
                time.sleep(delay)
                continue

        except subprocess.TimeoutExpired:
            last_error = "Timed out after 5 minutes"
            _log(f"{label} TIMEOUT (attempt {attempt}/{MAX_RETRIES})")
            if attempt < MAX_RETRIES:
                _log(f"{label} Retrying...")
                continue

        except Exception as e:
            last_error = str(e)
            _log(f"{label} ERROR: {e} (attempt {attempt}/{MAX_RETRIES})")
            if attempt < MAX_RETRIES:
                time.sleep(10)
                continue

    _log(f"{label} FAILED after {MAX_RETRIES} attempts.")
    return (batch_index, False, last_error)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="AI-powered batch document refinement",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Usage:")[0],
    )
    parser.add_argument(
        "documents_dir",
        type=Path,
        help="Directory containing JSON documents to refine",
    )
    parser.add_argument(
        "--goal",
        required=True,
        help="Refinement goal — a clear description of what to change in each document",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5,
        help="Number of files per sub-agent (default: 5)",
    )
    parser.add_argument(
        "--model",
        default="sonnet",
        help="Claude model to use for sub-agents (default: sonnet)",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=30,
        help="Max agent turns per batch (default: 30)",
    )
    parser.add_argument(
        "--pattern",
        default="*.json",
        help="Glob pattern for document files (default: *.json)",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=None,
        help="Path to schema file (auto-detected if not specified)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=5,
        help="Number of parallel sub-agents (default: 5)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process this many batches (for testing)",
    )
    parser.add_argument(
        "--reset-progress",
        action="store_true",
        help="Clear the progress ledger and start fresh",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show batch plan without executing",
    )

    args = parser.parse_args()

    # Resolve directory
    docs_dir = args.documents_dir.resolve()
    if not docs_dir.is_dir():
        print(f"Error: {docs_dir} is not a directory")
        sys.exit(1)

    # Progress ledger
    ledger_path = default_ledger_path(docs_dir)
    ledger = ProgressLedger(ledger_path)

    if args.reset_progress:
        ledger.reset()
        print(f"Progress ledger cleared: {ledger_path}")

    # Discover documents
    all_files = discover_documents(docs_dir, args.pattern)
    if not all_files:
        print(f"No files matching '{args.pattern}' in {docs_dir}")
        sys.exit(1)

    # Filter out already-completed files
    remaining_files = [f for f in all_files if not ledger.is_done(f.name)]
    skipped = len(all_files) - len(remaining_files)

    # Find schema
    schema_path = args.schema.resolve() if args.schema else find_schema(docs_dir)

    # Create batches from remaining files only
    batches = batch_files(remaining_files, args.batch_size)

    if args.limit is not None:
        batches = batches[:args.limit]

    total_batches = len(batches)

    # Print plan
    print("=" * 60)
    print("Document Refinement Plan")
    print("=" * 60)
    print(f"  Directory:      {docs_dir}")
    print(f"  Schema:         {schema_path or '(none)'}")
    print(f"  Total files:    {len(all_files)}")
    if skipped > 0:
        print(f"  Already done:   {skipped} (from {ledger_path.name})")
    print(f"  Remaining:      {len(remaining_files)}")
    print(f"  Batch size:     {args.batch_size}")
    print(f"  Batches to run: {total_batches}")
    if args.limit is not None:
        print(f"  Limit:          {args.limit} batches")
    print(f"  Workers:        {args.workers}")
    print(f"  Model:          {args.model}")
    print(f"  Retries:        {MAX_RETRIES} (backoff: {RETRY_BASE_DELAY}s, "
          f"{RETRY_BASE_DELAY*2}s, {RETRY_BASE_DELAY*4}s)")
    print(f"  Goal:           {args.goal[:100]}{'...' if len(args.goal) > 100 else ''}")
    print("=" * 60)

    if len(remaining_files) == 0:
        print("\nAll files already refined. Use --reset-progress to start over.")
        return

    if args.dry_run:
        print("\nDRY RUN — batch breakdown:\n")
        for i, batch in enumerate(batches):
            names = [f.name for f in batch]
            print(f"  Batch {i + 1}: {len(batch)} files")
            for name in names:
                print(f"    - {name}")
        print(f"\nWould invoke {total_batches} sub-agents. "
              f"Use without --dry-run to execute.")
        return

    # Execute batches in parallel
    print(f"\nStarting refinement with {args.workers} parallel workers...\n")
    start_time = time.time()

    results: list[tuple[int, bool, str]] = []

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {}
        for i, batch in enumerate(batches):
            future = executor.submit(
                run_batch,
                batch_index=i,
                total_batches=total_batches,
                file_paths=batch,
                goal=args.goal,
                schema_path=schema_path,
                model=args.model,
                max_turns=args.max_turns,
                ledger=ledger,
            )
            futures[future] = i

        for future in as_completed(futures):
            results.append(future.result())

    # Sort results by batch index for consistent reporting
    results.sort(key=lambda r: r[0])

    # Summary
    elapsed = time.time() - start_time
    succeeded = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)

    print("\n" + "=" * 60)
    print("Refinement Complete")
    print("=" * 60)
    print(f"  Batches run:     {len(results)}")
    print(f"  Succeeded:       {succeeded}")
    print(f"  Failed:          {failed}")
    print(f"  Total completed: {ledger.count}/{len(all_files)} files")
    print(f"  Elapsed:         {elapsed:.1f}s")
    print(f"  Ledger:          {ledger_path}")

    if failed > 0:
        print("\nFailed batches:")
        for idx, ok, msg in results:
            if not ok:
                print(f"  Batch {idx + 1}: {msg[:200]}")

        remaining_after = len(all_files) - ledger.count
        print(f"\n{remaining_after} files still need processing.")
        print(f"Re-run the same command to resume — completed files will be skipped.")


if __name__ == "__main__":
    main()
