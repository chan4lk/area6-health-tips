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
BRAND_COLOR_PRIMARY = "#f97316"    # orange-500

# Category label mapping for bottom bar
CATEGORY_LABELS: dict[str, str] = {
    "sleep":      "SLEEP & RECOVERY",
    "exercise":   "FITNESS",
    "nutrition":  "NUTRITION",
    "hydration":  "HYDRATION",
    "mental":     "MENTAL HEALTH",
    "posture":    "POSTURE",
    "habits":     "HEALTHY HABITS",
    "recovery":   "RECOVERY",
    "breathing":  "BREATHING",
    "gut-health": "GUT HEALTH",
}

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
    category: str = "",
) -> None:
    """
    Compose the final 1080x1920 video frame using Pillow, then mux with audio via FFmpeg.

    Matches the Area6 Stitch reference layout from qualitylife.lk:
      - Pure black background (#0a0a0a)
      - Top-left logo + "AREA 6" branding
      - Orange "HEALTH TIP" pill badge
      - Huge Sinhala title (last word orange)
      - White card at bottom with left orange accent bar and body tip text
      - Bottom bar with logo, handle, category label, and SUBSCRIBE button
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

    if not os.path.exists(font_sinh_bold_path):
        font_sinh_bold_path = font_sinh_reg_path
    if not os.path.exists(font_brand_bold_path):
        font_brand_bold_path = font_brand_reg_path

    def load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
        return ImageFont.load_default()

    fnt_area6      = load_font(font_brand_bold_path, 28)   # "AREA 6" top-left
    fnt_pill       = load_font(font_brand_bold_path, 26)   # "HEALTH TIP" pill
    fnt_title      = load_font(font_sinh_bold_path,  130)  # huge Sinhala title
    fnt_title_sm   = load_font(font_sinh_bold_path,  100)  # fallback if too many lines
    fnt_body       = load_font(font_sinh_reg_path,   52)   # body tip in card
    fnt_handle     = load_font(font_brand_bold_path, 28)   # @AREA6_OFFICIAL
    fnt_cat        = load_font(font_brand_reg_path,  22)   # category label
    fnt_subscribe  = load_font(font_brand_bold_path, 24)   # SUBSCRIBE button

    # ----------------------------------------------------------------- colors
    BG       = (10,  10,  10,  255)   # #0a0a0a
    WHITE    = (255, 255, 255, 255)
    ORANGE   = (249, 115, 22,  255)   # #f97316
    ORANGE_5 = (249, 115, 22,  13)    # 5% opacity for glow
    GRAY     = (153, 153, 153, 255)   # #999
    DARK     = (17,  17,  17,  255)   # #111111 for card text

    # ---------------------------------------------------------- base canvas
    frame = Image.new("RGBA", (WIDTH, HEIGHT), BG)
    draw  = ImageDraw.Draw(frame)

    # ----------------------------------------------- subtle orange glow (bottom-left)
    glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    glow_d = ImageDraw.Draw(glow)
    glow_d.ellipse([-100, HEIGHT - 350, 300, HEIGHT - 50], fill=ORANGE_5)
    frame = Image.alpha_composite(frame, glow)
    draw  = ImageDraw.Draw(frame)

    # =======================================================================
    # TOP BAR: logo (80x80, top-left, x=50, y=50) + "AREA 6"
    # =======================================================================
    LOGO_X    = 50
    LOGO_Y    = 50
    LOGO_SIZE = 80
    LOGO_RAD  = 14

    if LOGO_PATH.exists():
        logo = Image.open(LOGO_PATH).convert("RGBA")
        logo = logo.resize((LOGO_SIZE, LOGO_SIZE), Image.LANCZOS)
        lmask = Image.new("L", (LOGO_SIZE, LOGO_SIZE), 0)
        ImageDraw.Draw(lmask).rounded_rectangle(
            [0, 0, LOGO_SIZE - 1, LOGO_SIZE - 1], radius=LOGO_RAD, fill=255
        )
        logo.putalpha(lmask)
        frame.paste(logo, (LOGO_X, LOGO_Y), mask=logo)
        draw = ImageDraw.Draw(frame)  # refresh after paste

    area6_bbox = draw.textbbox((0, 0), "AREA 6", font=fnt_area6)
    area6_h    = area6_bbox[3] - area6_bbox[1]
    area6_y    = LOGO_Y + (LOGO_SIZE - area6_h) // 2
    draw.text((LOGO_X + LOGO_SIZE + 18, area6_y), "AREA 6", font=fnt_area6, fill=WHITE)

    # =======================================================================
    # ORANGE PILL BADGE: "HEALTH TIP" (y=180, x=60, ~220x60)
    # =======================================================================
    PILL_X = 60
    PILL_Y = 180
    PILL_W = 220
    PILL_H = 60
    draw.rounded_rectangle(
        [PILL_X, PILL_Y, PILL_X + PILL_W, PILL_Y + PILL_H],
        radius=PILL_H // 2,
        fill=ORANGE,
    )
    pill_text = "HEALTH TIP"
    pb = draw.textbbox((0, 0), pill_text, font=fnt_pill)
    draw.text(
        (PILL_X + (PILL_W - (pb[2] - pb[0])) // 2, PILL_Y + (PILL_H - (pb[3] - pb[1])) // 2),
        pill_text, font=fnt_pill, fill=WHITE,
    )

    # =======================================================================
    # HUGE TITLE (Sinhala, left-aligned x=60, starting y=280, last word orange)
    # =======================================================================
    TITLE_X           = 60
    TITLE_START_Y     = 280
    TITLE_LINE_EXTRA  = 20   # extra spacing between lines

    def wrap_words(words: list[str], max_chars: int = 10) -> list[list[str]]:
        """Wrap a word list into lines of at most max_chars characters."""
        lines: list[list[str]] = []
        current: list[str] = []
        current_len = 0
        for word in words:
            wl  = len(word)
            sep = 1 if current else 0
            if current and current_len + sep + wl > max_chars:
                lines.append(current)
                current     = [word]
                current_len = wl
            else:
                current.append(word)
                current_len += sep + wl
        if current:
            lines.append(current)
        return lines

    title_words = title.split()
    title_font  = fnt_title
    title_lines = wrap_words(title_words, max_chars=10)
    if len(title_lines) > 4:
        title_font  = fnt_title_sm
        title_lines = wrap_words(title_words, max_chars=10)
        title_lines = title_lines[:4]  # hard cap at 4

    line_h = title_font.size + TITLE_LINE_EXTRA

    for li, line_words in enumerate(title_lines):
        is_last = li == len(title_lines) - 1
        y = TITLE_START_Y + li * line_h
        x = TITLE_X
        if is_last:
            prefix = line_words[:-1]
            last_w = line_words[-1]
            if prefix:
                prefix_str = " ".join(prefix) + " "
                draw.text((x, y), prefix_str, font=title_font, fill=WHITE)
                pb2 = draw.textbbox((x, y), prefix_str, font=title_font)
                x = pb2[2]
            draw.text((x, y), last_w, font=title_font, fill=ORANGE)
        else:
            draw.text((x, y), " ".join(line_words), font=title_font, fill=WHITE)

    # =======================================================================
    # WHITE CARD (bottom ~28%, y ≈ 1350 – 1800)
    # =======================================================================
    CARD_MARGIN  = 30
    CARD_X       = CARD_MARGIN
    CARD_Y       = 1350
    CARD_BOTTOM  = 1800
    CARD_W       = WIDTH - 2 * CARD_MARGIN
    CARD_RADIUS  = 24
    ACCENT_W     = 8

    # Draw full orange card first, then white card offset by ACCENT_W so the
    # orange left strip + rounded corners show through.
    draw.rounded_rectangle(
        [CARD_X, CARD_Y, CARD_X + CARD_W, CARD_BOTTOM],
        radius=CARD_RADIUS, fill=ORANGE,
    )
    draw.rounded_rectangle(
        [CARD_X + ACCENT_W, CARD_Y, CARD_X + CARD_W, CARD_BOTTOM],
        radius=CARD_RADIUS, fill=(255, 255, 255, 255),
    )

    # Body tip text inside card
    BODY_X      = CARD_X + ACCENT_W + 30
    BODY_Y      = CARD_Y + 30
    body_lines  = _wrap_sinhala(subtitle_text, max_chars=16)
    body_line_h = fnt_body.size + 16
    for i, bline in enumerate(body_lines[:3]):
        draw.text((BODY_X, BODY_Y + i * body_line_h), bline, font=fnt_body, fill=DARK)

    # =======================================================================
    # BOTTOM BAR (y ≈ 1820)
    # =======================================================================
    BAR_Y        = 1820
    BAR_LOGO_SZ  = 60
    BAR_LOGO_RAD = 10

    if LOGO_PATH.exists():
        bar_logo = Image.open(LOGO_PATH).convert("RGBA")
        bar_logo = bar_logo.resize((BAR_LOGO_SZ, BAR_LOGO_SZ), Image.LANCZOS)
        blmask   = Image.new("L", (BAR_LOGO_SZ, BAR_LOGO_SZ), 0)
        ImageDraw.Draw(blmask).rounded_rectangle(
            [0, 0, BAR_LOGO_SZ - 1, BAR_LOGO_SZ - 1], radius=BAR_LOGO_RAD, fill=255
        )
        bar_logo.putalpha(blmask)
        frame.paste(bar_logo, (30, BAR_Y), mask=bar_logo)
        draw = ImageDraw.Draw(frame)

    TEXT_X = 30 + BAR_LOGO_SZ + 16
    draw.text((TEXT_X, BAR_Y + 2),  "@AREA6_OFFICIAL", font=fnt_handle, fill=WHITE)
    cat_label = CATEGORY_LABELS.get(category, "PERFORMANCE & RECOVERY")
    draw.text((TEXT_X, BAR_Y + 34), cat_label, font=fnt_cat, fill=GRAY)

    # SUBSCRIBE pill (right-aligned)
    sub_text = "SUBSCRIBE"
    sb = draw.textbbox((0, 0), sub_text, font=fnt_subscribe)
    sub_tw, sub_th = sb[2] - sb[0], sb[3] - sb[1]
    SP_X, SP_Y   = 24, 14
    sub_pw       = sub_tw + 2 * SP_X
    sub_ph       = sub_th + 2 * SP_Y
    sub_px       = WIDTH - 30 - sub_pw
    sub_py       = BAR_Y + (BAR_LOGO_SZ - sub_ph) // 2
    draw.rounded_rectangle(
        [sub_px, sub_py, sub_px + sub_pw, sub_py + sub_ph],
        radius=sub_ph // 2, fill=ORANGE,
    )
    draw.text((sub_px + SP_X, sub_py + SP_Y), sub_text, font=fnt_subscribe, fill=WHITE)

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

def generate_short(title: str, text: str, output_mp4: str, category: str = "") -> None:
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
            category=category,
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
        generate_short(title=tip["title"], text=tip["tip"], output_mp4=args.output, category=tip.get("category", ""))

    elif args.all:
        outdir = Path(args.outdir)
        outdir.mkdir(parents=True, exist_ok=True)
        tips = list_all_tips()
        print(f"\nProcessing {len(tips)} tips → {outdir}/")
        for tip_path in tips:
            tip = load_tip(str(tip_path))
            output_mp4 = str(outdir / f"{tip['id']}.mp4")
            print(f"\n[{tip['category']}] {tip['title']}")
            generate_short(title=tip["title"], text=tip["tip"], output_mp4=output_mp4, category=tip.get("category", ""))
        print(f"\nAll done. {len(tips)} videos written to {outdir}/")


if __name__ == "__main__":
    main()
