#!/usr/bin/env python3
"""
shorts_gen.py — YouTube Shorts pipeline for Area6 / qualitylife.lk

Generates a 9:16 vertical video (≤10s) with Sinhala TTS narration,
branded title, and subtitle overlay.

Usage:
    python shorts_gen.py --text "your sinhala text" --title "Slide Title" --output out.mp4
    python shorts_gen.py --narrative path/to/AUDIO-NARRATIVE-SI.md --slide 1 --output out.mp4
    python shorts_gen.py --narrative path/to/AUDIO-NARRATIVE-SI.md --all --outdir ./shorts/
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PIPER_MODEL = Path(__file__).parent / "piper" / "si_LK-sinhala-medium.onnx"
BRAND_NAME = "qualitylife.lk"  # Area6 branding — swap with full logo in video later

# Video specs
WIDTH = 1080
HEIGHT = 1920
FPS = 30
MAX_DURATION = 10.0  # seconds

# Sinhala speech rate estimate: ~3 words/second
WORDS_PER_SECOND = 3

# Font paths to try (Sinhala-capable Unicode font required)
SINHALA_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/noto/NotoSansSinhala-Regular.ttf",
    "/usr/share/fonts/noto/NotoSansSinhala-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

BRAND_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def find_font(candidates: list[str]) -> str:
    """Return the first existing font path from candidates, or empty string."""
    for path in candidates:
        if os.path.exists(path):
            return path
    return ""


def estimate_duration(text: str) -> float:
    """Rough estimate of spoken duration in seconds based on word count."""
    words = len(text.split())
    return words / WORDS_PER_SECOND


def truncate_to_fit(text: str, max_duration: float = MAX_DURATION) -> str:
    """Truncate text so estimated TTS duration fits within max_duration."""
    words = text.split()
    max_words = int(max_duration * WORDS_PER_SECOND)
    if len(words) <= max_words:
        return text
    truncated = words[:max_words]
    return " ".join(truncated) + "…"


def get_wav_duration(wav_path: str) -> float:
    """Return duration of a WAV file in seconds."""
    with wave.open(wav_path, "r") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        return frames / float(rate)


def wrap_text(text: str, max_chars_per_line: int = 40) -> str:
    """Simple word-wrap for FFmpeg drawtext (uses \\n as line separator)."""
    words = text.split()
    lines = []
    current = []
    current_len = 0

    for word in words:
        if current_len + len(word) + (1 if current else 0) > max_chars_per_line:
            if current:
                lines.append(" ".join(current))
            current = [word]
            current_len = len(word)
        else:
            if current:
                current_len += 1  # space
            current.append(word)
            current_len += len(word)

    if current:
        lines.append(" ".join(current))

    return r"\n".join(lines)


# ---------------------------------------------------------------------------
# Narrative parser
# ---------------------------------------------------------------------------

def parse_narrative(md_path: str) -> list[dict]:
    """
    Parse an AUDIO-NARRATIVE-SI.md file.

    Returns a list of dicts with keys:
        slide_number (int), title (str), text (str)
    """
    text = Path(md_path).read_text(encoding="utf-8")
    # Split on slide headings: ## Slide N — Title
    pattern = re.compile(
        r"^##\s+Slide\s+(\d+)\s*[—–-]+\s*(.+)$", re.MULTILINE
    )

    slides = []
    matches = list(pattern.finditer(text))

    for i, match in enumerate(matches):
        slide_num = int(match.group(1))
        title = match.group(2).strip()

        # Content is between this heading and the next separator or heading
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end]

        # Strip leading/trailing whitespace and remove trailing ---
        content = re.sub(r"\n---\s*$", "", content.strip())
        content = content.strip()

        slides.append({"slide_number": slide_num, "title": title, "text": content})

    return slides


def get_slide(md_path: str, slide_number: int) -> dict:
    """Return a single slide dict by number."""
    slides = parse_narrative(md_path)
    for slide in slides:
        if slide["slide_number"] == slide_number:
            return slide
    raise ValueError(f"Slide {slide_number} not found in {md_path}")


# ---------------------------------------------------------------------------
# TTS synthesis
# ---------------------------------------------------------------------------

def synthesize_tts(text: str, output_wav: str) -> None:
    """
    Generate Sinhala speech using Piper TTS.

    Requires piper-tts package and si_LK-sinhala-medium.onnx model in ./piper/.
    """
    try:
        import warnings
        warnings.filterwarnings("ignore")
        import numpy as np
        from piper import PiperVoice  # type: ignore
    except ImportError:
        print("ERROR: piper-tts not installed. Run: pip install piper-tts", file=sys.stderr)
        sys.exit(1)

    if not PIPER_MODEL.exists():
        print(
            f"ERROR: Piper model not found at {PIPER_MODEL}\n"
            "Download si_LK-sinhala-medium.onnx from Piper releases and place it in ./piper/",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"  [TTS] Loading Piper model...", end=" ", flush=True)
    voice = PiperVoice.load(str(PIPER_MODEL))
    print("done")
    print(f"  [TTS] Synthesizing speech → {output_wav}")

    # synthesize_wav sets WAV format automatically (channels, rate, bit depth)
    with wave.open(output_wav, "wb") as wf:
        voice.synthesize_wav(text, wf, set_wav_format=True)


# ---------------------------------------------------------------------------
# Video generation
# ---------------------------------------------------------------------------

def build_video(
    title: str,
    subtitle_text: str,
    audio_wav: str,
    output_mp4: str,
    duration: float,
) -> None:
    """
    Compose the final video using FFmpeg.

    Layout (1080x1920, 9:16 vertical):
      - Dark gradient background (#1a1a2e → #16213e)
      - Brand name at top (small, white)
      - Title in center (large, gold/white)
      - Subtitle (Sinhala) in bottom third (white, word-wrapped)
    """
    sinhala_font = find_font(SINHALA_FONT_CANDIDATES)
    brand_font = find_font(BRAND_FONT_CANDIDATES)

    if not sinhala_font:
        print(
            "WARNING: No Sinhala-capable font found. Text may not render correctly.\n"
            "Install a Sinhala font (e.g. fonts-noto-core) for proper rendering.",
            file=sys.stderr,
        )
        sinhala_font = brand_font or ""

    if not brand_font:
        brand_font = sinhala_font or ""

    # Escape text for FFmpeg drawtext (colons, backslashes, quotes are special)
    def ffmpeg_escape(s: str) -> str:
        s = s.replace("\\", "\\\\")
        s = s.replace("'", "\u2019")   # replace straight apostrophe with typographic
        s = s.replace(":", r"\:")
        return s

    wrapped_subtitle = wrap_text(subtitle_text, max_chars_per_line=38)
    escaped_title = ffmpeg_escape(title)
    escaped_subtitle = ffmpeg_escape(wrapped_subtitle)
    escaped_brand = ffmpeg_escape(BRAND_NAME)

    # Build FFmpeg filter chain
    # 1. Gradient background via two colored rectangles (top→bottom blend)
    # 2. Brand name at top
    # 3. Title in center
    # 4. Subtitle at bottom third

    font_args_brand = f"fontfile={brand_font}:" if brand_font else ""
    font_args_sinhala = f"fontfile={sinhala_font}:" if sinhala_font else ""

    vf_parts = [
        # Gradient: draw dark blue rectangle full frame, then overlay slightly lighter at top
        f"drawbox=x=0:y=0:w={WIDTH}:h={HEIGHT}:color=#1a1a2e@1.0:t=fill",
        f"drawbox=x=0:y=0:w={WIDTH}:h={int(HEIGHT * 0.4)}:color=#16213e@0.6:t=fill",
        # Brand name — top, centered, small
        (
            f"drawtext={font_args_brand}"
            f"text='{escaped_brand}':"
            f"fontcolor=white:fontsize=42:alpha=0.85:"
            f"x=(w-text_w)/2:y=80"
        ),
        # Decorative line under brand
        f"drawbox=x={WIDTH//2 - 200}:y=145:w=400:h=3:color=#e2b04a@0.9:t=fill",
        # Title — centered vertically (slightly above center)
        (
            f"drawtext={font_args_brand}"
            f"text='{escaped_title}':"
            f"fontcolor=#e2b04a:fontsize=72:alpha=1.0:"
            f"x=(w-text_w)/2:y=(h-text_h)/2-80:"
            f"line_spacing=12"
        ),
        # Subtitle (Sinhala) — bottom third
        (
            f"drawtext={font_args_sinhala}"
            f"text='{escaped_subtitle}':"
            f"fontcolor=white:fontsize=52:alpha=0.95:"
            f"x=(w-text_w)/2:y=h*0.68:"
            f"line_spacing=14"
        ),
    ]

    vf = ",".join(vf_parts)

    cmd = [
        "ffmpeg", "-y",
        # Input 1: generated video (lavfi color source)
        "-f", "lavfi",
        "-i", f"color=c=#1a1a2e:s={WIDTH}x{HEIGHT}:r={FPS}:d={duration:.3f}",
        # Input 2: TTS audio
        "-i", audio_wav,
        # Video filter chain
        "-vf", vf,
        # Encoding
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "22",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        "-movflags", "+faststart",
        "-pix_fmt", "yuv420p",
        output_mp4,
    ]

    print(f"  [FFmpeg] Rendering video → {output_mp4}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("FFmpeg error:", result.stderr[-2000:], file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def generate_short(title: str, text: str, output_mp4: str) -> None:
    """Full pipeline: text → TTS → video → MP4."""
    # 1. Truncate text to fit ≤10s
    text = truncate_to_fit(text)
    estimated = estimate_duration(text)
    print(f"  [Text] '{text[:60]}{'…' if len(text) > 60 else ''}'")
    print(f"  [Text] Estimated duration: {estimated:.1f}s ({len(text.split())} words)")

    with tempfile.TemporaryDirectory() as tmpdir:
        wav_path = os.path.join(tmpdir, "narration.wav")

        # 2. Generate TTS audio
        synthesize_tts(text, wav_path)

        # 3. Get actual audio duration
        actual_duration = get_wav_duration(wav_path)
        actual_duration = min(actual_duration, MAX_DURATION)
        print(f"  [Audio] Actual duration: {actual_duration:.2f}s")

        # 4. Render video
        build_video(
            title=title,
            subtitle_text=text,
            audio_wav=wav_path,
            output_mp4=output_mp4,
            duration=actual_duration,
        )

    print(f"  [Done] → {output_mp4}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate YouTube Shorts from Sinhala narration text."
    )

    # Input modes
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--text", help="Sinhala narration text to use directly")
    input_group.add_argument(
        "--narrative", help="Path to AUDIO-NARRATIVE-SI.md file"
    )

    # Narrative sub-options
    parser.add_argument(
        "--slide", type=int, help="Slide number to extract from narrative"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all slides from narrative",
    )

    # Output options
    parser.add_argument("--title", default="", help="Slide/video title text")
    parser.add_argument("--output", help="Output MP4 file path (single slide mode)")
    parser.add_argument(
        "--outdir",
        default="./shorts",
        help="Output directory for --all mode (default: ./shorts)",
    )

    args = parser.parse_args()

    if args.text:
        # Direct text mode
        if not args.output:
            parser.error("--output is required when using --text")
        title = args.title or "qualitylife.lk"
        print(f"\nGenerating Short: '{title}'")
        generate_short(title=title, text=args.text, output_mp4=args.output)

    elif args.narrative:
        if args.all:
            # Batch mode: process all slides
            outdir = Path(args.outdir)
            outdir.mkdir(parents=True, exist_ok=True)
            slides = parse_narrative(args.narrative)
            print(f"\nProcessing {len(slides)} slides → {outdir}/")
            for slide in slides:
                output_mp4 = str(outdir / f"slide_{slide['slide_number']:03d}.mp4")
                print(f"\n[Slide {slide['slide_number']}] {slide['title']}")
                generate_short(
                    title=slide["title"],
                    text=slide["text"],
                    output_mp4=output_mp4,
                )
        elif args.slide:
            # Single slide from narrative
            if not args.output:
                parser.error("--output is required when using --narrative --slide N")
            slide = get_slide(args.narrative, args.slide)
            print(f"\nGenerating Short: Slide {slide['slide_number']} — {slide['title']}")
            generate_short(
                title=slide["title"],
                text=slide["text"],
                output_mp4=args.output,
            )
        else:
            parser.error("With --narrative, specify --slide N or --all")


if __name__ == "__main__":
    main()
