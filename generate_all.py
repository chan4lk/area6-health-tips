#!/usr/bin/env python3
"""
generate_all.py — Batch generate all Area6 health tip Shorts.

Processes every JSON file in content/tips/ and writes one MP4 per tip
into the output/ directory.

Usage:
    python3 generate_all.py
    python3 generate_all.py --outdir /path/to/output
"""

import argparse
import subprocess
import sys
from pathlib import Path

TIPS_DIR = Path(__file__).parent / "content" / "tips"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch generate all health tip Shorts from content/tips/."
    )
    parser.add_argument(
        "--outdir",
        default="./output",
        help="Output directory for generated MP4s (default: ./output)",
    )
    args = parser.parse_args()

    tips = sorted(TIPS_DIR.glob("*.json"))
    if not tips:
        print(f"ERROR: No tip files found in {TIPS_DIR}", file=sys.stderr)
        sys.exit(1)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"Found {len(tips)} tip(s) in {TIPS_DIR}")
    print(f"Output directory: {outdir}\n")

    failed = []
    for tip_path in tips:
        output_mp4 = outdir / f"{tip_path.stem}.mp4"
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
    ok = total - len(failed)
    print(f"Done: {ok}/{total} videos generated in {outdir}/")
    if failed:
        print(f"Failed: {', '.join(failed)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
