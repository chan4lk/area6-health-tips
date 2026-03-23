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

PIPER_MODEL_SINHALA = Path(__file__).parent / "piper" / "si_LK-sinhala-medium.onnx"
PIPER_MODEL_ENGLISH = Path(__file__).parent / "piper" / "en_US-lessac-medium.onnx"
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
    str(Path.home() / ".local/share/fonts/NotoSansSinhala-Regular.ttf"),
    "/usr/share/fonts/truetype/noto/NotoSansSinhala-Regular.ttf",
    "/usr/share/fonts/noto/NotoSansSinhala-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

BRAND_FONT_CANDIDATES = [
    str(Path.home() / ".local/share/fonts/NotoSans-Bold.ttf"),
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

def _detect_language(text: str) -> str:
    """Detect if text is primarily Sinhala or English."""
    sinhala_chars = sum(1 for c in text if '\u0D80' <= c <= '\u0DFF')
    return "si" if sinhala_chars > len(text) * 0.3 else "en"


def synthesize_tts(text: str, output_wav: str, lang: str = "auto") -> None:
    """
    Generate speech using Piper TTS. Auto-detects language.
    """
    try:
        import warnings
        warnings.filterwarnings("ignore")
        import numpy as np
        from piper import PiperVoice  # type: ignore
    except ImportError:
        print("ERROR: piper-tts not installed. Run: pip install piper-tts", file=sys.stderr)
        sys.exit(1)

    if lang == "auto":
        lang = _detect_language(text)

    model_path = PIPER_MODEL_SINHALA if lang == "si" else PIPER_MODEL_ENGLISH

    if not model_path.exists():
        print(
            f"ERROR: Piper model not found at {model_path}\n"
            f"Download the {'Sinhala' if lang == 'si' else 'English'} model and place it in ./piper/",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"  [TTS] Loading Piper model ({lang})...", end=" ", flush=True)
    voice = PiperVoice.load(str(model_path))
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
    highlight: str = "",
) -> None:
    """
    Compose the final 1080x1920 video frame using Pillow, then mux with audio via FFmpeg.

    Area6 redesign:
      - Pure black background (#000000)
      - Faint AREA6 watermark rotated -15° in orange
      - Top bar: "≡ AREA6" left, logo circle top-right
      - Orange pill badge: "HEALTH TIPS // CATEGORY"
      - Huge Sinhala title with highlight word in orange (#f97316)
      - Left side vertical "PERFORMANCE // AREA6" text at 40% alpha
      - Dark semi-transparent info card with "DID YOU KNOW?" header
      - Bottom bar: logo circle, handle, category, SUBSCRIBE pill
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("ERROR: Pillow not installed. Run: pip install Pillow", file=sys.stderr)
        sys.exit(1)

    # ------------------------------------------------------------------ fonts
    _home = str(Path.home())
    font_brand_bold_path = find_font([
        f"{_home}/.local/share/fonts/NotoSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ])
    font_brand_reg_path  = find_font([
        f"{_home}/.local/share/fonts/NotoSans-Regular.ttf",
        f"{_home}/.local/share/fonts/NotoSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ])
    font_sinh_bold_path  = find_font([
        f"{_home}/.local/share/fonts/NotoSansSinhala-Bold.ttf",
        f"{_home}/.local/share/fonts/NotoSansSinhala-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansSinhala-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansSinhala-Regular.ttf",
    ])
    font_sinh_reg_path   = find_font([
        f"{_home}/.local/share/fonts/NotoSansSinhala-Regular.ttf",
        f"{_home}/.local/share/fonts/NotoSansSinhala-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansSinhala-Regular.ttf",
    ])

    if not os.path.exists(font_sinh_bold_path):
        font_sinh_bold_path = font_sinh_reg_path
    if not os.path.exists(font_brand_bold_path):
        font_brand_bold_path = font_brand_reg_path

    def load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
        return ImageFont.load_default()

    fnt_watermark = load_font(font_brand_bold_path, 380)
    fnt_menu      = load_font(font_brand_reg_path,  40)
    fnt_brand     = load_font(font_brand_bold_path, 44)
    fnt_pill      = load_font(font_brand_bold_path, 24)
    fnt_title     = load_font(font_sinh_bold_path,  140)
    fnt_title_sm  = load_font(font_sinh_bold_path,  110)
    fnt_vertical  = load_font(font_brand_bold_path, 20)
    fnt_did_know  = load_font(font_brand_bold_path, 28)
    fnt_body      = load_font(font_sinh_reg_path,   44)
    fnt_handle    = load_font(font_brand_bold_path, 26)
    fnt_cat       = load_font(font_brand_reg_path,  20)
    fnt_subscribe = load_font(font_brand_bold_path, 24)

    # ----------------------------------------------------------------- colors
    BG     = (0,   0,   0,   255)   # pure black
    WHITE  = (255, 255, 255, 255)
    ORANGE = (249, 115, 22,  255)   # #f97316
    GRAY   = (153, 153, 153, 255)   # #999

    # ---------------------------------------------------------- base canvas
    # Try category-specific background first, then fallback to default
    bg_cat_path = Path(__file__).parent / "branding" / "backgrounds" / f"{category}.png"
    bg_default_path = Path(__file__).parent / "branding" / "background.png"
    bg_path = bg_cat_path if bg_cat_path.exists() else bg_default_path
    if bg_path.exists():
        bg_img = Image.open(bg_path).convert("RGBA")
        bg_img = bg_img.resize((WIDTH, HEIGHT), Image.LANCZOS)
        frame = bg_img
    else:
        frame = Image.new("RGBA", (WIDTH, HEIGHT), BG)
        # Fallback watermark when no background image
        wm_canvas = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        wm_draw   = ImageDraw.Draw(wm_canvas)
        wm_bb     = wm_draw.textbbox((0, 0), "AREA6", font=fnt_watermark)
        wm_text_w = wm_bb[2] - wm_bb[0]
        wm_text_h = wm_bb[3] - wm_bb[1]
        wm_x      = (WIDTH - wm_text_w) // 2
        wm_y      = 900 - wm_text_h // 2
        wm_draw.text((wm_x, wm_y), "AREA6", font=fnt_watermark, fill=(249, 115, 22, 15))
        wm_canvas = wm_canvas.rotate(15)
        frame     = Image.alpha_composite(frame, wm_canvas)
    draw  = ImageDraw.Draw(frame)

    # Top bar is baked into the background image — skip drawing it again.

    # =======================================================================
    # ORANGE PILL BADGE (y=155, x=50): "HEALTH TIPS // CATEGORY"
    # =======================================================================
    cat_label = CATEGORY_LABELS.get(category, "PERFORMANCE & RECOVERY")
    pill_text = f"HEALTH TIPS // {cat_label}"
    pb        = draw.textbbox((0, 0), pill_text, font=fnt_pill)
    pill_tw   = pb[2] - pb[0]
    pill_th   = pb[3] - pb[1]
    PILL_X    = 50
    PILL_Y    = 155
    PILL_H    = 52
    PILL_W    = pill_tw + 40
    draw.rounded_rectangle(
        [PILL_X, PILL_Y, PILL_X + PILL_W, PILL_Y + PILL_H],
        radius=PILL_H // 2,
        fill=ORANGE,
    )
    draw.text(
        (PILL_X + 20, PILL_Y + (PILL_H - pill_th) // 2),
        pill_text, font=fnt_pill, fill=WHITE,
    )

    # =======================================================================
    # HUGE TITLE (y=240, x=50): highlight word in orange, others white
    # =======================================================================
    TITLE_X       = 50
    TITLE_START_Y = 240
    LINE_SPACING  = 15

    def wrap_title_words(words: list[str], max_chars: int = 8) -> list[list[str]]:
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

    is_english = _detect_language(title) == "en"
    title_wrap_chars = 15 if is_english else 8

    # Use brand font for English titles, Sinhala font for Sinhala
    if is_english:
        fnt_title    = load_font(font_brand_bold_path, 100)
        fnt_title_sm = load_font(font_brand_bold_path, 80)
        fnt_body     = load_font(font_brand_reg_path,  38)

    title_words = title.split()
    title_font  = fnt_title
    title_lines = wrap_title_words(title_words, max_chars=title_wrap_chars)
    if len(title_lines) > 3:
        title_font  = fnt_title_sm
        title_lines = wrap_title_words(title_words, max_chars=title_wrap_chars)

    line_h = title_font.size + LINE_SPACING

    for li, line_words in enumerate(title_lines):
        y = TITLE_START_Y + li * line_h
        x = TITLE_X
        for wi, word in enumerate(line_words):
            is_last_word = (li == len(title_lines) - 1 and wi == len(line_words) - 1)
            use_orange   = (highlight and word == highlight) or (not highlight and is_last_word)
            color        = ORANGE if use_orange else WHITE
            draw.text((x, y), word, font=title_font, fill=color)
            wb = draw.textbbox((x, y), word + " ", font=title_font)
            x  = wb[2]

    # =======================================================================
    # LEFT SIDE VERTICAL TEXT (x=22, vertically centered)
    # "PERFORMANCE // AREA6" rotated 90° CCW → reads bottom to top
    # =======================================================================
    vert_text = "PERFORMANCE // AREA6"
    vt_bb     = draw.textbbox((0, 0), vert_text, font=fnt_vertical)
    vt_w      = vt_bb[2] - vt_bb[0]
    vt_h      = vt_bb[3] - vt_bb[1]
    vt_pad    = 4
    vt_img    = Image.new("RGBA", (vt_w + vt_pad * 2, vt_h + vt_pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(vt_img).text((vt_pad, vt_pad), vert_text, font=fnt_vertical,
                                fill=(249, 115, 22, 102))
    vt_img    = vt_img.rotate(90, expand=True)   # 90° CCW → text reads upward
    vt_dest_x = max(0, 22 - vt_img.size[0] // 2)
    vt_dest_y = max(0, (HEIGHT - vt_img.size[1]) // 2)
    frame.alpha_composite(vt_img, dest=(vt_dest_x, vt_dest_y))
    draw = ImageDraw.Draw(frame)

    # =======================================================================
    # DARK INFO CARD (bottom ~35%): semi-transparent, orange accent, DID YOU KNOW?
    # =======================================================================
    CARD_MARGIN  = 30
    CARD_X       = CARD_MARGIN
    CARD_W       = WIDTH - 2 * CARD_MARGIN
    CARD_RADIUS  = 24
    ACCENT_W     = 8
    BODY_PAD_X   = 30
    BODY_PAD_TOP = 28
    BODY_PAD_BOT = 28
    DYK_H        = 28 + 16   # "DID YOU KNOW?" line height + gap below

    body_wrap_chars = 38 if _detect_language(subtitle_text) == "en" else 20
    body_lines  = _wrap_sinhala(subtitle_text, max_chars=body_wrap_chars)
    body_line_h = fnt_body.size + 14
    card_text_h = len(body_lines) * body_line_h
    card_h      = BODY_PAD_TOP + DYK_H + card_text_h + BODY_PAD_BOT

    CARD_BOTTOM = HEIGHT - 110
    CARD_Y      = CARD_BOTTOM - card_h

    # Semi-transparent dark card + orange left accent via overlay
    card_overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    card_draw    = ImageDraw.Draw(card_overlay)
    card_draw.rounded_rectangle(
        [CARD_X, CARD_Y, CARD_X + CARD_W, CARD_BOTTOM],
        radius=CARD_RADIUS, fill=(249, 115, 22, 255),
    )
    card_draw.rounded_rectangle(
        [CARD_X + ACCENT_W, CARD_Y, CARD_X + CARD_W, CARD_BOTTOM],
        radius=CARD_RADIUS, fill=(26, 26, 26, 230),
    )
    frame = Image.alpha_composite(frame, card_overlay)
    draw  = ImageDraw.Draw(frame)

    draw.text(
        (CARD_X + ACCENT_W + BODY_PAD_X, CARD_Y + BODY_PAD_TOP),
        "DID YOU KNOW?", font=fnt_did_know, fill=ORANGE,
    )

    BODY_X = CARD_X + ACCENT_W + BODY_PAD_X
    BODY_Y = CARD_Y + BODY_PAD_TOP + DYK_H
    for i, bline in enumerate(body_lines):
        draw.text((BODY_X, BODY_Y + i * body_line_h), bline, font=fnt_body, fill=WHITE)

    # =======================================================================
    # BOTTOM BAR (HEIGHT-100 to HEIGHT)
    # =======================================================================
    BAR_Y = HEIGHT - 100
    draw.rectangle([0, BAR_Y, WIDTH, HEIGHT], fill=BG)

    BAR_LOGO_SZ = 60
    if LOGO_PATH.exists():
        bar_logo = Image.open(LOGO_PATH).convert("RGBA")
        bar_logo = bar_logo.resize((BAR_LOGO_SZ, BAR_LOGO_SZ), Image.LANCZOS)
        blmask   = Image.new("L", (BAR_LOGO_SZ, BAR_LOGO_SZ), 0)
        ImageDraw.Draw(blmask).ellipse([0, 0, BAR_LOGO_SZ - 1, BAR_LOGO_SZ - 1], fill=255)
        bar_logo.putalpha(blmask)
        frame.paste(bar_logo, (30, BAR_Y + 20), mask=bar_logo)
        draw = ImageDraw.Draw(frame)

    TEXT_X = 30 + BAR_LOGO_SZ + 16
    draw.text((TEXT_X, BAR_Y + 18), "@AREA6_OFFICIAL", font=fnt_handle, fill=WHITE)
    draw.text((TEXT_X, BAR_Y + 52), cat_label,          font=fnt_cat,    fill=GRAY)

    sub_text = "SUBSCRIBE"
    sb       = draw.textbbox((0, 0), sub_text, font=fnt_subscribe)
    sub_tw   = sb[2] - sb[0]
    sub_th   = sb[3] - sb[1]
    SP_X     = 24
    SP_Y     = 14
    sub_pw   = sub_tw + 2 * SP_X
    sub_ph   = sub_th + 2 * SP_Y
    sub_px   = WIDTH - 30 - sub_pw
    sub_py   = BAR_Y + (100 - sub_ph) // 2
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

def generate_short(title: str, text: str, output_mp4: str, category: str = "", highlight: str = "") -> None:
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
            highlight=highlight,
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
        generate_short(title=tip["title"], text=tip["tip"], output_mp4=args.output, category=tip.get("category", ""), highlight=tip.get("highlight", ""))

    elif args.all:
        outdir = Path(args.outdir)
        outdir.mkdir(parents=True, exist_ok=True)
        tips = list_all_tips()
        print(f"\nProcessing {len(tips)} tips → {outdir}/")
        for tip_path in tips:
            tip = load_tip(str(tip_path))
            output_mp4 = str(outdir / f"{tip['id']}.mp4")
            print(f"\n[{tip['category']}] {tip['title']}")
            generate_short(title=tip["title"], text=tip["tip"], output_mp4=output_mp4, category=tip.get("category", ""), highlight=tip.get("highlight", ""))
        print(f"\nAll done. {len(tips)} videos written to {outdir}/")


if __name__ == "__main__":
    main()
