#!/usr/bin/env python3
"""
generate_all.py — Batch generate Area6 health tip Shorts.

Processes tip JSONs from a dated batch folder and writes MP4s to the
matching output folder.

Usage:
    python3 generate_all.py 2026-03-23-en          # specific batch
    python3 generate_all.py                         # latest batch
    python3 generate_all.py --list                  # list all batches
"""

import argparse
import subprocess
import sys
from pathlib import Path

TIPS_DIR = Path(__file__).parent / "content" / "tips"
OUTPUT_DIR = Path(__file__).parent / "output"


def list_batches() -> list[str]:
    """List all batch folders in content/tips/."""
    return sorted(d.name for d in TIPS_DIR.iterdir() if d.is_dir())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch generate health tip Shorts from a dated folder."
    )
    parser.add_argument("batch", nargs="?", help="Batch folder name (e.g. 2026-03-23-en). Defaults to latest.")
    parser.add_argument("--list", action="store_true", help="List available batches")
    parser.add_argument("--skip-existing", action="store_true", help="Skip if MP4 already exists")
    args = parser.parse_args()

    if args.list:
        batches = list_batches()
        if not batches:
            print("No batches found.")
        for b in batches:
            count = len(list((TIPS_DIR / b).glob("*.json")))
            vids = len(list((OUTPUT_DIR / b).glob("*.mp4"))) if (OUTPUT_DIR / b).exists() else 0
            print(f"  {b}: {count} tips, {vids} videos")
        return

    batches = list_batches()
    if not batches:
        print(f"ERROR: No batch folders in {TIPS_DIR}", file=sys.stderr)
        sys.exit(1)

    batch = args.batch or batches[-1]
    tips_path = TIPS_DIR / batch
    out_path = OUTPUT_DIR / batch

    if not tips_path.exists():
        print(f"ERROR: Batch folder not found: {tips_path}", file=sys.stderr)
        print(f"Available: {', '.join(batches)}")
        sys.exit(1)

    tips = sorted(tips_path.glob("*.json"))
    if not tips:
        print(f"ERROR: No tip files in {tips_path}", file=sys.stderr)
        sys.exit(1)

    out_path.mkdir(parents=True, exist_ok=True)

    print(f"Batch: {batch}")
    print(f"Found {len(tips)} tip(s)")
    print(f"Output: {out_path}\n")

    failed = []
    skipped = 0
    for tip_path in tips:
        output_mp4 = out_path / f"{tip_path.stem}.mp4"
        if args.skip_existing and output_mp4.exists():
            skipped += 1
            continue
        print(f"--- {tip_path.name} ---")
        result = subprocess.run(
            [sys.executable, "shorts_gen.py", "--tip", str(tip_path), "--output", str(output_mp4)],
            cwd=Path(__file__).parent,
        )
        if result.returncode != 0:
            print(f"  FAILED: {tip_path.name}")
            failed.append(tip_path.name)
        print()

    total = len(tips)
    ok = total - len(failed) - skipped
    print(f"Done: {ok} generated, {skipped} skipped, {len(failed)} failed (of {total})")
    if failed:
        print(f"Failed: {', '.join(failed)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
