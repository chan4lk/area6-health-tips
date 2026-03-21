#!/usr/bin/env python3
"""
shorts_gen.py — YouTube Shorts pipeline for Area6 / qualitylife.lk

Generates a 9:16 vertical video (≤10s) with Sinhala TTS narration,
branded title, and subtitle overlay from a JSON tip file.

Usage:
    python3 shorts_gen.py --tip content/tips/hydration.json --output output/hydration.mp4
    python3 shorts_gen.py --all --outdir output/
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PIPER_MODEL = Path(__file__).parent / "piper" / "si_LK-sinhala-medium.onnx"
LOGO_PATH = Path(__file__).parent / "branding" / "logo.jpg"
TIPS_DIR = Path(__file__).parent / "content" / "tips"

# Area 6 brand identity (from qualitylife.lk)
BRAND_LINE1 = "Area 6"
BRAND_LINE2 = "Quality Life Fitness"
BRAND_COLOR_PRIMARY = "#f97316"    # orange-500
BRAND_COLOR_ACCENT  = "#f59e0b"    # amber-500
BRAND_BG_DARK       = "#030712"    # gray-950 (hero bg)
BRAND_BG_MID        = "#111827"    # gray-900

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
# Content loader
# ---------------------------------------------------------------------------

def load_tip(json_path: str) -> dict:
    """Load a tip JSON file and return its contents."""
    path = Path(json_path)
    if not path.exists():
        print(f"ERROR: Tip file not found: {json_path}", file=sys.stderr)
        sys.exit(1)
    with path.open(encoding="utf-8") as f:
        tip = json.load(f)
    required = {"id", "title", "tip"}
    missing = required - tip.keys()
    if missing:
        print(f"ERROR: Tip file {json_path} is missing fields: {missing}", file=sys.stderr)
        sys.exit(1)
    return tip


def list_all_tips() -> list[Path]:
    """Return all JSON tip files in content/tips/, sorted by name."""
    if not TIPS_DIR.exists():
        print(f"ERROR: Tips directory not found: {TIPS_DIR}", file=sys.stderr)
        sys.exit(1)
    tips = sorted(TIPS_DIR.glob("*.json"))
    if not tips:
        print(f"ERROR: No .json files found in {TIPS_DIR}", file=sys.stderr)
        sys.exit(1)
    return tips


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
    escaped_brand1 = ffmpeg_escape(BRAND_LINE1)
    escaped_brand2 = ffmpeg_escape(BRAND_LINE2)

    font_args_brand = f"fontfile={brand_font}:" if brand_font else ""
    font_args_sinhala = f"fontfile={sinhala_font}:" if sinhala_font else ""

    # Logo overlay: scale to 120x120, position top-center
    logo_filter = ""
    has_logo = LOGO_PATH.exists()
    if has_logo:
        logo_filter = f"[1:v]scale=120:120[logo];[base][logo]overlay=(W-w)/2:60[with_logo];"
        logo_input_tag = "[with_logo]"
    else:
        logo_input_tag = "[base]"

    # Build filter chain
    vf_parts = [
        # Area 6 dark background (gray-950)
        f"drawbox=x=0:y=0:w={WIDTH}:h={HEIGHT}:color={BRAND_BG_DARK}@1.0:t=fill",
        # Subtle orange glow at bottom (brand energy)
        f"drawbox=x=0:y={int(HEIGHT*0.75)}:w={WIDTH}:h={int(HEIGHT*0.25)}:color={BRAND_COLOR_PRIMARY}@0.08:t=fill",
    ]

    base_filter = ",".join(vf_parts)

    # Text overlays (applied after logo if present)
    text_parts = [
        # "Area 6" — below logo, bold, white
        (
            f"drawtext={font_args_brand}"
            f"text='{escaped_brand1}':"
            f"fontcolor=white:fontsize=56:alpha=1.0:"
            f"x=(w-text_w)/2:y=200"
        ),
        # "Quality Life Fitness" — subtitle brand line, orange
        (
            f"drawtext={font_args_brand}"
            f"text='{escaped_brand2}':"
            f"fontcolor={BRAND_COLOR_PRIMARY}:fontsize=36:alpha=0.95:"
            f"x=(w-text_w)/2:y=270"
        ),
        # Orange accent line under brand
        f"drawbox=x={WIDTH//2 - 220}:y=330:w=440:h=4:color={BRAND_COLOR_PRIMARY}@1.0:t=fill",
        # Tip title — center of frame, amber/gold
        (
            f"drawtext={font_args_brand}"
            f"text='{escaped_title}':"
            f"fontcolor={BRAND_COLOR_ACCENT}:fontsize=68:alpha=1.0:"
            f"x=(w-text_w)/2:y=(h-text_h)/2-60:"
            f"line_spacing=10"
        ),
        # Sinhala tip text — bottom third, white
        (
            f"drawtext={font_args_sinhala}"
            f"text='{escaped_subtitle}':"
            f"fontcolor=white:fontsize=50:alpha=0.95:"
            f"x=(w-text_w)/2:y=h*0.70:"
            f"line_spacing=14"
        ),
        # "qualitylife.lk" watermark — very bottom, subtle
        (
            f"drawtext={font_args_brand}"
            f"text='qualitylife.lk':"
            f"fontcolor={BRAND_COLOR_PRIMARY}:fontsize=30:alpha=0.7:"
            f"x=(w-text_w)/2:y=h-60"
        ),
    ]

    if has_logo:
        # With logo: base → logo overlay → text
        full_filter = (
            f"[0:v]{base_filter}[base];"
            f"{logo_filter}"
            f"{logo_input_tag}" + ",".join(text_parts)
        )
        cmd_inputs = [
            "-f", "lavfi", "-i", f"color=c={BRAND_BG_DARK}:s={WIDTH}x{HEIGHT}:r={FPS}:d={duration:.3f}",
            "-loop", "1", "-i", str(LOGO_PATH),
            "-i", audio_wav,
        ]
        audio_stream = "2:a"
    else:
        full_filter = f"[0:v]{base_filter}," + ",".join(text_parts)
        cmd_inputs = [
            "-f", "lavfi", "-i", f"color=c={BRAND_BG_DARK}:s={WIDTH}x{HEIGHT}:r={FPS}:d={duration:.3f}",
            "-i", audio_wav,
        ]
        audio_stream = "1:a"

    if has_logo:
        cmd = [
            "ffmpeg", "-y",
            *cmd_inputs,
            "-filter_complex", full_filter,
            "-map", "[with_logo]" if "[with_logo]" not in full_filter else "0:v",
            "-map", audio_stream,
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest", "-movflags", "+faststart", "-pix_fmt", "yuv420p",
            output_mp4,
        ]
        # Simpler: just use -vf with logo as overlay via filter_complex
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c={BRAND_BG_DARK}:s={WIDTH}x{HEIGHT}:r={FPS}:d={duration:.3f}",
            "-loop", "1", "-i", str(LOGO_PATH),
            "-i", audio_wav,
            "-filter_complex",
            (
                f"[1:v]scale=120:120[logo];"
                f"[0:v]{','.join(vf_parts)}[bg];"
                f"[bg][logo]overlay=(W-w)/2:60[with_logo];"
                f"[with_logo]{','.join(text_parts)}[out]"
            ),
            "-map", "[out]", "-map", "2:a",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest", "-movflags", "+faststart", "-pix_fmt", "yuv420p",
            output_mp4,
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c={BRAND_BG_DARK}:s={WIDTH}x{HEIGHT}:r={FPS}:d={duration:.3f}",
            "-i", audio_wav,
            "-vf", ",".join(vf_parts + text_parts),
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest", "-movflags", "+faststart", "-pix_fmt", "yuv420p",
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
        description="Generate YouTube Shorts from Sinhala health tip JSON files."
    )

    # Input modes
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--tip",
        help="Path to a single tip JSON file (e.g. content/tips/hydration.json)",
    )
    input_group.add_argument(
        "--all",
        action="store_true",
        help="Process all tips in content/tips/ and write to --outdir",
    )

    # Output options
    parser.add_argument("--output", help="Output MP4 file path (single tip mode)")
    parser.add_argument(
        "--outdir",
        default="./output",
        help="Output directory for --all mode (default: ./output)",
    )

    args = parser.parse_args()

    if args.tip:
        if not args.output:
            parser.error("--output is required when using --tip")
        tip = load_tip(args.tip)
        print(f"\nGenerating Short: [{tip['category']}] {tip['title']}")
        generate_short(title=tip["title"], text=tip["tip"], output_mp4=args.output)

    elif args.all:
        outdir = Path(args.outdir)
        outdir.mkdir(parents=True, exist_ok=True)
        tips = list_all_tips()
        print(f"\nProcessing {len(tips)} tips → {outdir}/")
        for tip_path in tips:
            tip = load_tip(str(tip_path))
            output_mp4 = str(outdir / f"{tip['id']}.mp4")
            print(f"\n[{tip['category']}] {tip['title']}")
            generate_short(title=tip["title"], text=tip["tip"], output_mp4=output_mp4)
        print(f"\nAll done. {len(tips)} videos written to {outdir}/")


if __name__ == "__main__":
    main()
