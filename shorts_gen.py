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

def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert a #rrggbb hex string to an (R, G, B) tuple."""
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _wrap_sinhala(text: str, max_chars: int = 18) -> list[str]:
    """
    Word-wrap Sinhala text into lines of at most max_chars characters.
    Sinhala glyphs are wide, so we use a tighter limit than Latin text.
    """
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    current_len = 0

    for word in words:
        word_len = len(word)
        if current and current_len + 1 + word_len > max_chars:
            lines.append(" ".join(current))
            current = [word]
            current_len = word_len
        else:
            if current:
                current_len += 1  # space
            current.append(word)
            current_len += word_len

    if current:
        lines.append(" ".join(current))

    return lines


def _draw_text_centered(
    draw,
    text: str,
    font,
    y: int,
    canvas_width: int,
    fill: tuple,
) -> int:
    """Draw text horizontally centered on the canvas. Returns the text height."""
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (canvas_width - text_w) // 2
    draw.text((x, y), text, font=font, fill=fill)
    return text_h


def build_video(
    title: str,
    subtitle_text: str,
    audio_wav: str,
    output_mp4: str,
    duration: float,
) -> None:
    """
    Compose the final 1080x1920 video frame using Pillow, then mux with audio via FFmpeg.

    Using Pillow (instead of FFmpeg drawtext) ensures correct rendering of Sinhala
    complex script — FFmpeg's drawtext filter cannot handle the ligature shaping
    required by Sinhala Unicode text.

    Layout:
      - Dark background (#030712) filling the full frame
      - Area 6 logo (120x120, rounded corners) centered at top
      - "Area 6" (NotoSans-Bold, 56px, white) below logo
      - "Quality Life Fitness" (NotoSans-Regular, 36px, #f97316 orange) below that
      - Orange separator line (440x4px, #f97316)
      - Tip title (NotoSansSinhala, 68px, #f59e0b amber) vertically centered
      - Tip body (NotoSansSinhala, 50px, white) in bottom 30% of frame
      - "qualitylife.lk" watermark (30px, #f97316, 70% alpha) at very bottom
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("ERROR: Pillow not installed. Run: pip install Pillow", file=sys.stderr)
        sys.exit(1)

    # ------------------------------------------------------------------ fonts
    font_brand_bold_path = "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"
    font_brand_reg_path  = "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"
    font_sinh_bold_path  = "/usr/share/fonts/truetype/noto/NotoSansSinhala-Bold.ttf"
    font_sinh_reg_path   = "/usr/share/fonts/truetype/noto/NotoSansSinhala-Regular.ttf"

    # Fallback to Regular if Bold variant is missing
    if not os.path.exists(font_sinh_bold_path):
        font_sinh_bold_path = font_sinh_reg_path
    if not os.path.exists(font_brand_bold_path):
        font_brand_bold_path = font_brand_reg_path

    def load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
        # Last-resort fallback to Pillow's built-in bitmap font
        return ImageFont.load_default()

    fnt_brand_name  = load_font(font_brand_bold_path, 56)   # "Area 6"
    fnt_brand_sub   = load_font(font_brand_reg_path,  36)   # "Quality Life Fitness"
    fnt_title       = load_font(font_sinh_bold_path,  68)   # Sinhala title
    fnt_tip         = load_font(font_sinh_reg_path,   50)   # Sinhala tip body
    fnt_watermark   = load_font(font_brand_reg_path,  30)   # watermark

    # --------------------------------------------------------------- colours
    bg_color      = _hex_to_rgb(BRAND_BG_DARK)           # #030712
    orange        = _hex_to_rgb(BRAND_COLOR_PRIMARY)      # #f97316
    amber         = _hex_to_rgb(BRAND_COLOR_ACCENT)       # #f59e0b
    white         = (255, 255, 255, 255)
    orange_full   = (*orange, 255)
    amber_full    = (*amber,  255)
    orange_70     = (*orange, int(255 * 0.70))            # watermark alpha

    # ---------------------------------------------------------- base canvas
    frame = Image.new("RGBA", (WIDTH, HEIGHT), (*bg_color, 255))
    draw  = ImageDraw.Draw(frame)

    # --------------------------------------------------- logo (top-center)
    LOGO_Y      = 60
    LOGO_SIZE   = 120
    LOGO_RADIUS = 24   # rounded-corner radius

    if LOGO_PATH.exists():
        logo = Image.open(LOGO_PATH).convert("RGBA")
        logo = logo.resize((LOGO_SIZE, LOGO_SIZE), Image.LANCZOS)

        # Build a circular/rounded-corner mask
        mask = Image.new("L", (LOGO_SIZE, LOGO_SIZE), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle(
            [0, 0, LOGO_SIZE - 1, LOGO_SIZE - 1],
            radius=LOGO_RADIUS,
            fill=255,
        )
        logo.putalpha(mask)

        logo_x = (WIDTH - LOGO_SIZE) // 2
        frame.paste(logo, (logo_x, LOGO_Y), mask=logo)

    # ------------------------------------------- brand text below logo
    BRAND_NAME_Y = LOGO_Y + LOGO_SIZE + 20   # ≈ 200
    _draw_text_centered(draw, BRAND_LINE1, fnt_brand_name, BRAND_NAME_Y, WIDTH, white)

    BRAND_SUB_Y = BRAND_NAME_Y + 70          # ≈ 270
    _draw_text_centered(draw, BRAND_LINE2, fnt_brand_sub, BRAND_SUB_Y, WIDTH, orange_full)

    # ----------------------------------------------- orange separator line
    SEP_Y      = BRAND_SUB_Y + 50            # ≈ 320
    SEP_W      = 440
    SEP_H      = 4
    sep_x      = (WIDTH - SEP_W) // 2
    draw.rectangle([sep_x, SEP_Y, sep_x + SEP_W, SEP_Y + SEP_H], fill=orange_full)

    # ------------------------------------------------ Sinhala title (center)
    # Measure title height and center it vertically in the upper-mid region
    title_bbox = draw.textbbox((0, 0), title, font=fnt_title)
    title_h    = title_bbox[3] - title_bbox[1]
    TITLE_Y    = (HEIGHT // 2) - (title_h // 2) - 60
    _draw_text_centered(draw, title, fnt_title, TITLE_Y, WIDTH, amber_full)

    # ------------------------------------------- Sinhala tip body (bottom 30%)
    # Word-wrap at ~18 Sinhala chars per line, then stack lines from y=70%
    tip_lines  = _wrap_sinhala(subtitle_text, max_chars=18)
    LINE_H     = fnt_tip.size + 18   # font size + inter-line gap
    TIP_START_Y = int(HEIGHT * 0.70)

    for i, line in enumerate(tip_lines):
        y = TIP_START_Y + i * LINE_H
        if y + LINE_H > HEIGHT - 80:
            # Clip lines that overflow into the watermark zone
            break
        _draw_text_centered(draw, line, fnt_tip, y, WIDTH, white)

    # --------------------------------------------------- watermark (bottom)
    WATERMARK_Y = HEIGHT - 65
    wm_layer    = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    wm_draw     = ImageDraw.Draw(wm_layer)
    _draw_text_centered(wm_draw, "qualitylife.lk", fnt_watermark, WATERMARK_Y, WIDTH, orange_70)
    frame = Image.alpha_composite(frame, wm_layer)

    # ---------------------------------------------------- save frame as PNG
    frame_rgb = frame.convert("RGB")

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_png:
        frame_path = tmp_png.name
    frame_rgb.save(frame_path, "PNG")
    print(f"  [Pillow] Frame saved → {frame_path}")

    # ------------------------------------------ FFmpeg: static frame + audio
    print(f"  [FFmpeg] Muxing video → {output_mp4}")
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", frame_path,
        "-i", audio_wav,
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        "-movflags", "+faststart",
        "-pix_fmt", "yuv420p",
        output_mp4,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    # Clean up temp frame regardless of FFmpeg outcome
    try:
        os.unlink(frame_path)
    except OSError:
        pass

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
