#!/usr/bin/env python3
"""
extract_shorts.py — Batch extractor for YouTube Shorts-worthy snippets

Reads an AUDIO-NARRATIVE-SI.md file and extracts the most punchy/intro
paragraph from each slide section, trimmed to ≤10 seconds of spoken content.

Usage:
    python extract_shorts.py path/to/AUDIO-NARRATIVE-SI.md --output shorts_plan.json
"""

import argparse
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_DURATION = 10.0          # seconds
WORDS_PER_SECOND = 3         # Sinhala speech rate estimate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def estimate_duration(text: str) -> float:
    """Rough estimate of spoken duration in seconds based on word count."""
    words = len(text.split())
    return words / WORDS_PER_SECOND


def truncate_to_fit(text: str, max_duration: float = MAX_DURATION) -> str:
    """
    Trim text so the estimated TTS duration fits within max_duration.
    Appends an ellipsis if truncation occurs.
    """
    words = text.split()
    max_words = int(max_duration * WORDS_PER_SECOND)
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "…"


def extract_first_paragraph(text: str) -> str:
    """
    Extract the first non-empty paragraph from a slide's text body.

    Paragraphs are separated by blank lines. This is typically the most
    impactful/intro sentence — ideal for a Short.
    """
    paragraphs = re.split(r"\n\s*\n", text.strip())
    for para in paragraphs:
        cleaned = para.strip()
        if cleaned:
            # Collapse internal newlines to spaces
            return re.sub(r"\s+", " ", cleaned)
    return text.strip()


# ---------------------------------------------------------------------------
# Narrative parser
# ---------------------------------------------------------------------------

def parse_narrative(md_path: str) -> list[dict]:
    """
    Parse an AUDIO-NARRATIVE-SI.md file.

    Returns a list of dicts:
        slide_number (int), title (str), text (str — full slide body)
    """
    content = Path(md_path).read_text(encoding="utf-8")

    # Match headings like: ## Slide 1 — Title  or  ## Slide 1 - Title
    heading_pattern = re.compile(
        r"^##\s+Slide\s+(\d+)\s*[—–-]+\s*(.+)$", re.MULTILINE
    )

    slides = []
    matches = list(heading_pattern.finditer(content))

    for i, match in enumerate(matches):
        slide_num = int(match.group(1))
        title = match.group(2).strip()

        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        body = content[start:end]

        # Remove trailing separator lines
        body = re.sub(r"\n---\s*$", "", body.strip()).strip()

        slides.append({"slide_number": slide_num, "title": title, "text": body})

    return slides


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------

def extract_shorts_plan(md_path: str) -> list[dict]:
    """
    Extract Short-worthy snippets from all slides in a narrative file.

    For each slide:
    - Takes the first paragraph (most punchy intro text)
    - Trims to ≤10s of estimated spoken content
    - Records slide number, title, text snippet, estimated duration

    Returns a list of snippet dicts.
    """
    slides = parse_narrative(md_path)

    if not slides:
        print(
            f"WARNING: No slides found in {md_path}.\n"
            "Ensure headings match the format:  ## Slide N — Title",
            file=sys.stderr,
        )
        return []

    snippets = []
    for slide in slides:
        # Extract most impactful (first) paragraph
        first_para = extract_first_paragraph(slide["text"])

        # Truncate to ≤10s
        snippet_text = truncate_to_fit(first_para)
        est_duration = estimate_duration(snippet_text)

        was_truncated = snippet_text != first_para

        snippets.append(
            {
                "slide_number": slide["slide_number"],
                "title": slide["title"],
                "text": snippet_text,
                "estimated_duration": round(est_duration, 2),
                "word_count": len(snippet_text.split()),
                "was_truncated": was_truncated,
            }
        )

    return snippets


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract Shorts-worthy snippets from an AUDIO-NARRATIVE-SI.md file."
    )
    parser.add_argument(
        "narrative",
        help="Path to AUDIO-NARRATIVE-SI.md",
    )
    parser.add_argument(
        "--output",
        default="shorts_plan.json",
        help="Output JSON file path (default: shorts_plan.json)",
    )
    parser.add_argument(
        "--max-duration",
        type=float,
        default=MAX_DURATION,
        help=f"Maximum allowed duration in seconds (default: {MAX_DURATION})",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        dest="print_output",
        help="Also print the plan to stdout",
    )

    args = parser.parse_args()

    if not Path(args.narrative).exists():
        print(f"ERROR: File not found: {args.narrative}", file=sys.stderr)
        sys.exit(1)

    # Allow overriding MAX_DURATION
    global MAX_DURATION
    MAX_DURATION = args.max_duration

    print(f"Parsing: {args.narrative}")
    snippets = extract_shorts_plan(args.narrative)

    print(f"Found {len(snippets)} slides.")

    # Count how many were truncated
    truncated = sum(1 for s in snippets if s["was_truncated"])
    if truncated:
        print(f"  {truncated} slide(s) were truncated to fit ≤{args.max_duration}s.")

    # Write JSON output
    output_path = Path(args.output)
    output_path.write_text(
        json.dumps(snippets, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Saved plan → {output_path}")

    if args.print_output:
        print("\n" + json.dumps(snippets, ensure_ascii=False, indent=2))

    # Summary table
    print("\nSummary:")
    print(f"  {'Slide':<7} {'Duration':>9}  {'Words':>6}  {'Truncated':>10}  Title")
    print("  " + "-" * 65)
    for s in snippets:
        trunc_marker = "yes" if s["was_truncated"] else ""
        print(
            f"  {s['slide_number']:<7} {s['estimated_duration']:>7.1f}s"
            f"  {s['word_count']:>6}  {trunc_marker:>10}  {s['title']}"
        )


if __name__ == "__main__":
    main()
