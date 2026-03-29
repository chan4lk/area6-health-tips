#!/usr/bin/env python3
"""
reel_gen.py — Generate a branded health tip Reel with multi-scene AI visuals.

Reads a tip JSON and produces a 15-20s vertical video with:
  - Reusable branded intro (2s) + outro (3s)
  - 3 AI-generated scenes with Ken Burns camera movement
  - Static logo + watermark overlay on content scenes
  - Calm Piper TTS narration starting after intro
  - Lo-fi background music throughout

Usage:
    python3 reel_gen.py --tip content/tips/2026-03-23-en/hydration-brain.json
    python3 reel_gen.py --tip content/tips/2026-03-23-en/hydration-brain.json --output output/reels/hydration-brain.mp4
    python3 reel_gen.py --tip content/tips/2026-03-23-en/hydration-brain.json --no-imagen  # use category backgrounds instead
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
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent
BRAND_DIR = ROOT / "branding" / "reel-assets"
CONFIG_PATH = BRAND_DIR / "reel-config.json"
FFMPEG = os.path.expanduser("~/.npm-global/bin/ffmpeg")
PIPER_MODEL = ROOT / "piper" / "en_US-lessac-medium.onnx"

# ---------------------------------------------------------------------------
# Load config
# ---------------------------------------------------------------------------
def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)

# ---------------------------------------------------------------------------
# Font + drawing helpers
# ---------------------------------------------------------------------------
def load_font(path, size):
    from PIL import ImageFont
    return ImageFont.truetype(os.path.expanduser(path), size)


def shadow_text(draw, pos, text, font, fill, offset=3):
    x, y = pos
    for dx, dy in [(offset, offset), (offset, 0), (0, offset), (-1, offset)]:
        draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0))
    draw.text(pos, text, font=font, fill=fill)


def center_x(draw, text, font, width=1080):
    bb = draw.textbbox((0, 0), text, font=font)
    return (width - (bb[2] - bb[0])) // 2

# ---------------------------------------------------------------------------
# Detect language
# ---------------------------------------------------------------------------
def detect_language(text):
    sinhala = sum(1 for c in text if '\u0D80' <= c <= '\u0DFF')
    return "si" if sinhala > len(text) * 0.3 else "en"

# ---------------------------------------------------------------------------
# Generate scene images with Imagen
# ---------------------------------------------------------------------------
def generate_scene_images(tip, config, tmpdir):
    """Generate 3 AI scene images for the tip using Imagen 4."""
    from google import genai
    from google.genai import types
    import io, time

    env_file = ROOT / ".env"
    api_key = None
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("GEMINI_API_KEY="):
                api_key = line.split("=", 1)[1].strip()
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY not found", file=sys.stderr)
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    suffix = config["imagen"]["prompt_suffix"]
    category = tip.get("category", "health")
    title = tip.get("title", "Health Tip")
    tip_text = tip.get("tip", "")

    # Use Gemini to generate scene prompts
    from google.genai import types as gtypes
    prompt_gen = client.models.generate_content(
        model="gemini-2.5-flash",
        config=gtypes.GenerateContentConfig(temperature=0.8),
        contents=f"""Generate 3 image prompts for a health tip video about: "{title}" — {tip_text}

Category: {category}

Each prompt should describe a cinematic 9:16 vertical photo for these scenes:
1. HOOK scene — dramatic visual that grabs attention related to the topic
2. FACT scene — visual that illustrates the health science/fact
3. CTA scene — inspiring visual that motivates action

Rules:
- Professional cinematic photography style
- Dark moody lighting with orange accents
- No text, no watermarks, no logos in the image
- Each prompt should be 1-2 sentences max
- Fitness/health/wellness aesthetic

Output ONLY a JSON array of 3 strings, no explanation:
["prompt1", "prompt2", "prompt3"]""",
    )

    raw = prompt_gen.text.strip()
    if raw.startswith("```"):
        raw = "\n".join(raw.split("\n")[1:])
        raw = raw.rsplit("```", 1)[0].strip()
    scene_prompts = json.loads(raw)

    images = []
    for i, prompt in enumerate(scene_prompts):
        full_prompt = prompt + suffix
        print(f"  [Imagen] Scene {i+1}: {prompt[:60]}...")
        try:
            result = client.models.generate_images(
                model=config["imagen"]["model"],
                prompt=full_prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio=config["imagen"]["aspect_ratio"],
                    output_mime_type="image/png",
                ),
            )
            from PIL import Image
            img = Image.open(io.BytesIO(result.generated_images[0].image.image_bytes))
            img = img.resize((1080, 1920), Image.LANCZOS)
            path = os.path.join(tmpdir, f"scene_{i+1}.png")
            img.save(path)
            images.append(path)
            print(f"  [Imagen] Scene {i+1} ✅")
        except Exception as e:
            print(f"  [Imagen] Scene {i+1} failed: {e}")
            # Fallback: use category background
            fallback = ROOT / "branding" / "backgrounds" / f"{category}.png"
            if not fallback.exists():
                fallback = ROOT / "branding" / "background.png"
            if fallback.exists():
                from PIL import Image
                img = Image.open(fallback).resize((1080, 1920), Image.LANCZOS)
                path = os.path.join(tmpdir, f"scene_{i+1}.png")
                img.save(path)
                images.append(path)
                print(f"  [Imagen] Scene {i+1} using fallback background")
            else:
                print(f"  ERROR: No fallback background found", file=sys.stderr)
                sys.exit(1)
        if i < 2:
            time.sleep(2)

    return images


def use_category_backgrounds(tip, config, tmpdir):
    """Use category backgrounds instead of Imagen (--no-imagen mode)."""
    from PIL import Image
    category = tip.get("category", "health")
    fallback = ROOT / "branding" / "backgrounds" / f"{category}.png"
    if not fallback.exists():
        fallback = ROOT / "branding" / "background.png"

    images = []
    for i in range(3):
        img = Image.open(fallback).resize((1080, 1920), Image.LANCZOS)
        path = os.path.join(tmpdir, f"scene_{i+1}.png")
        img.save(path)
        images.append(path)
    return images

# ---------------------------------------------------------------------------
# Generate text overlay PNGs
# ---------------------------------------------------------------------------
def generate_text_overlays(tip, config, tmpdir):
    """Create transparent PNG overlays with text for each scene."""
    from PIL import Image, ImageDraw

    font_path = config["visuals"]["font"]
    ORANGE = tuple(int(config["visuals"]["colors"]["orange"].lstrip("#")[i:i+2], 16) for i in (0,2,4))
    WHITE = (255, 255, 255)

    logo_raw = Image.open(ROOT / config["visuals"]["logo"]).convert("RGBA")
    logo_size = config["visuals"]["logo_size"]
    logo_sm = logo_raw.resize((logo_size, logo_size), Image.LANCZOS)
    mask_sm = Image.new("L", (logo_size, logo_size), 0)
    ImageDraw.Draw(mask_sm).ellipse([0, 0, logo_size, logo_size], fill=255)

    logo_pos = config["visuals"]["logo_position"]
    wm_text = config["visuals"]["watermark_text"]
    wm_y = config["visuals"]["watermark_y"]
    fnt_wm = load_font(font_path, 18)

    title = tip.get("title", "Health Tip")
    tip_text = tip.get("tip", "")
    highlight = tip.get("highlight", "")

    # Split tip text into ~3 parts for 3 scenes
    words = tip_text.split()
    total = len(words)
    s1_words = words[:total//3]
    s2_words = words[total//3:2*total//3]
    s3_words = words[2*total//3:]

    scene_texts = [
        # Scene 1: Hook - title emphasis
        [
            ("DID YOU KNOW?", load_font(font_path, 36), ORANGE, 160),
            *_split_title(title, highlight, font_path, ORANGE, WHITE),
        ],
        # Scene 2: Fact - middle part of narration
        [
            (" ".join(s2_words[:4]), load_font(font_path, 44), WHITE, 1350),
            (" ".join(s2_words[4:8]) if len(s2_words) > 4 else "", load_font(font_path, 52), ORANGE, 1410),
            (" ".join(s2_words[8:]) if len(s2_words) > 8 else "", load_font(font_path, 44), WHITE, 1475),
        ],
        # Scene 3: CTA - last part
        [
            (" ".join(s3_words[:5]), load_font(font_path, 48), WHITE, 750),
            (" ".join(s3_words[5:]) if len(s3_words) > 5 else "", load_font(font_path, 56), ORANGE, 820),
        ],
    ]

    overlays = []
    for i, texts in enumerate(scene_texts):
        img = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        for text, font, color, y in texts:
            if not text.strip():
                continue
            bb = d.textbbox((0, 0), text, font=font)
            tw = bb[2] - bb[0]
            x = (1080 - tw) // 2
            for dx, dy in [(3,3),(3,0),(0,3),(-1,3)]:
                d.text((x+dx, y+dy), text, font=font, fill=(0, 0, 0, 220))
            d.text((x, y), text, font=font, fill=color)

        # Static logo
        img.paste(logo_sm, tuple(logo_pos), mask_sm)

        # Watermark centered under... well, bottom center
        bb = d.textbbox((0, 0), wm_text, font=fnt_wm)
        tw = bb[2] - bb[0]
        wm_x = (1080 - tw) // 2
        for dx, dy in [(1,1),(1,0),(0,1)]:
            d.text((wm_x+dx, wm_y+dy), wm_text, font=fnt_wm, fill=(0,0,0,180))
        d.text((wm_x, wm_y), wm_text, font=fnt_wm, fill=(255,255,255,200))

        path = os.path.join(tmpdir, f"text_{i+1}.png")
        img.save(path)
        overlays.append(path)

    return overlays


def _split_title(title, highlight, font_path, orange, white):
    """Split title into lines with highlight word in orange."""
    words = title.split()
    if len(words) <= 4:
        line1 = " ".join(words[:2])
        line2 = " ".join(words[2:])
    else:
        mid = len(words) // 2
        line1 = " ".join(words[:mid])
        line2 = " ".join(words[mid:])

    # Check if highlight is in line1 or line2
    fnt_big = load_font(font_path, 64)
    fnt_orange = load_font(font_path, 72)

    result = []
    if line1:
        color = orange if highlight and highlight.lower() in line1.lower() else white
        result.append((line1, fnt_big if color == white else fnt_orange, color, 700))
    if line2:
        color = orange if highlight and highlight.lower() in line2.lower() else white
        result.append((line2, fnt_big if color == white else fnt_orange, color, 775))

    return result

# ---------------------------------------------------------------------------
# TTS synthesis
# ---------------------------------------------------------------------------
def synthesize_narration(text, config, output_wav):
    """Generate calm narration with Piper TTS."""
    import warnings
    warnings.filterwarnings("ignore")
    from piper import PiperVoice
    from piper.voice import SynthesisConfig

    tts_cfg = config["tts"]
    model = ROOT / tts_cfg["model"]
    length_scale = tts_cfg.get("length_scale", 1.15)

    print(f"  [TTS] Loading Piper ({length_scale}x calm)...", end=" ", flush=True)
    voice = PiperVoice.load(str(model))
    print("done")

    syn_cfg = SynthesisConfig(length_scale=length_scale)
    with wave.open(output_wav, "wb") as wf:
        voice.synthesize_wav(text, wf, set_wav_format=True, syn_config=syn_cfg)

    # Return duration
    with wave.open(output_wav, "rb") as wf:
        dur = wf.getnframes() / wf.getframerate()
    print(f"  [TTS] Narration: {dur:.1f}s → {output_wav}")
    return dur

# ---------------------------------------------------------------------------
# Video assembly
# ---------------------------------------------------------------------------
def encode_scene(image_path, duration, kb_filter_template, output_path):
    """Encode a scene with Ken Burns effect."""
    frames = int(duration * 30)
    vf = kb_filter_template.replace("{frames}", str(frames))
    subprocess.run([FFMPEG, "-y", "-loop", "1", "-i", image_path,
        "-t", str(duration), "-vf", vf,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast",
        output_path], capture_output=True)


def overlay_text(video_path, text_png, output_path):
    """Overlay a transparent PNG on a video."""
    r = subprocess.run([FFMPEG, "-y", "-i", video_path, "-i", text_png,
        "-filter_complex", "[0:v][1:v]overlay=0:0",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast",
        output_path], capture_output=True)
    if r.returncode != 0:
        # Fallback: copy without overlay
        subprocess.run(["cp", video_path, output_path])


def mix_audio(bgm_path, narration_path, narration_dur, total_dur, config, output_path):
    """Mix BGM + delayed narration."""
    audio_cfg = config["audio"]
    voice_delay = int(config["timing"]["voice_delay"] * 1000)
    bgm_vol = audio_cfg["bgm_volume"]
    fade_out_start = total_dur - audio_cfg["bgm_fade_out"]

    subprocess.run([FFMPEG, "-y",
        "-i", bgm_path, "-i", narration_path,
        "-filter_complex",
        f"[0:a]atrim=0:{total_dur},volume={bgm_vol},"
        f"afade=t=in:st=0:d={audio_cfg['bgm_fade_in']},"
        f"afade=t=out:st={fade_out_start}:d={audio_cfg['bgm_fade_out']}[bgm];"
        f"[1:a]adelay={voice_delay}|{voice_delay},volume={audio_cfg['voice_volume']}[voice];"
        f"[bgm][voice]amix=inputs=2:weights=1 1:duration=first,atrim=0:{total_dur}[aout]",
        "-map", "[aout]", "-c:a", "aac", "-b:a",
        config["format"]["audio_bitrate"],
        output_path], capture_output=True)


def build_reel(tip, config, scene_images, text_overlays, narration_wav, narration_dur, output_path, tmpdir):
    """Assemble the full reel."""
    timing = config["timing"]
    structure = config["structure"]
    kb = config["ken_burns_filters"]

    intro_dur = structure["intro"]["duration"]
    outro_dur = structure["outro"]["duration"]
    voice_buffer = timing["voice_buffer_after"]
    content_dur = narration_dur + voice_buffer
    total_dur = intro_dur + content_dur + outro_dur

    # Scene durations based on distribution
    dist = structure["scenes"]["distribution"]
    scene_durs = [round(content_dur * d, 1) for d in dist]
    # Adjust last scene to avoid rounding drift
    scene_durs[-1] = round(content_dur - sum(scene_durs[:-1]), 1)

    kb_styles = structure["scenes"]["ken_burns_styles"]

    print(f"\n  [Build] Total: {total_dur:.1f}s (intro:{intro_dur} + content:{content_dur:.1f} + outro:{outro_dur})")
    print(f"  [Build] Scenes: {scene_durs[0]}s + {scene_durs[1]}s + {scene_durs[2]}s")

    # Encode content scenes
    scene_clips = []
    for i in range(3):
        clean = os.path.join(tmpdir, f"clean_{i}.mp4")
        final = os.path.join(tmpdir, f"final_{i}.mp4")

        encode_scene(scene_images[i], scene_durs[i], kb[kb_styles[i]], clean)
        overlay_text(clean, text_overlays[i], final)
        scene_clips.append(final)
        print(f"  [Build] Scene {i+1}: {scene_durs[i]}s ✅")

    # Encode outro with correct duration
    outro_clip = os.path.join(tmpdir, "outro.mp4")
    encode_scene(str(ROOT / structure["outro"]["frame"]),
                 outro_dur, kb[structure["outro"]["ken_burns"]], outro_clip)

    # Concat: intro + scenes + outro
    concat_file = os.path.join(tmpdir, "concat.txt")
    with open(concat_file, "w") as f:
        f.write(f"file '{(ROOT / structure['intro']['clip']).resolve()}'\n")
        for clip in scene_clips:
            f.write(f"file '{clip}'\n")
        f.write(f"file '{outro_clip}'\n")

    video_path = os.path.join(tmpdir, "video.mp4")
    subprocess.run([FFMPEG, "-y", "-f", "concat", "-safe", "0",
        "-i", concat_file, "-c", "copy", video_path], capture_output=True)

    # Mix audio
    audio_path = os.path.join(tmpdir, "audio.m4a")
    bgm_path = str(ROOT / config["audio"]["bgm"])
    mix_audio(bgm_path, narration_wav, narration_dur, total_dur, config, audio_path)

    # Final mux
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([FFMPEG, "-y",
        "-i", video_path, "-i", audio_path,
        "-c:v", "copy", "-c:a", "copy",
        "-t", str(total_dur),
        output_path], capture_output=True)

    size = Path(output_path).stat().st_size / 1024
    print(f"\n  ✅ {output_path} ({size:.0f} KB, {total_dur:.1f}s)")
    return output_path

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Generate a branded health tip Reel")
    parser.add_argument("--tip", required=True, help="Path to tip JSON file")
    parser.add_argument("--output", help="Output MP4 path (default: output/reels/<id>.mp4)")
    parser.add_argument("--no-imagen", action="store_true", help="Use category backgrounds instead of AI scenes")
    args = parser.parse_args()

    # Load tip
    tip = json.loads(Path(args.tip).read_text())
    tip_id = tip.get("id", Path(args.tip).stem)
    print(f"Generating Reel: [{tip.get('category', '?')}] {tip.get('title', tip_id)}")

    # Load config
    config = load_config()

    # Output path
    output = args.output or str(ROOT / "output" / "reels" / f"{tip_id}.mp4")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Step 1: Generate narration first (determines timing)
        narration_wav = os.path.join(tmpdir, "narration.wav")
        narration_dur = synthesize_narration(tip["tip"], config, narration_wav)

        # Step 2: Generate scene images
        if args.no_imagen:
            print("  [Scenes] Using category backgrounds...")
            scene_images = use_category_backgrounds(tip, config, tmpdir)
        else:
            print("  [Scenes] Generating AI images...")
            scene_images = generate_scene_images(tip, config, tmpdir)

        # Step 3: Generate text overlays
        print("  [Text] Building overlays...")
        text_overlays = generate_text_overlays(tip, config, tmpdir)

        # Step 4: Build reel
        build_reel(tip, config, scene_images, text_overlays,
                   narration_wav, narration_dur, output, tmpdir)

    print(f"\n[Done] → {output}")


if __name__ == "__main__":
    main()
