#!/usr/bin/env python3
"""
generate_batch.py — Full Area6 health shorts pipeline.

Calls Claude Haiku to generate Sinhala health tip scripts,
saves them as JSON, runs the video pipeline, and optionally pushes to GitHub.

Usage:
    python3 generate_batch.py --categories "hydration,sleep,exercise" --count 3
    python3 generate_batch.py --categories "nutrition,mental" --count 5 --no-push
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_DIR = Path(__file__).parent.parent.parent / "area6-health-tips"
TIPS_DIR = REPO_DIR / "content" / "tips"

SYSTEM_PROMPT = (
    "You are a health content writer for Area 6 - Quality Life Fitness (qualitylife.lk), "
    "a premium gym in Kadawatha, Sri Lanka. You write engaging Sinhala health tips for "
    "YouTube Shorts. Output ONLY valid JSON array, no explanation, no markdown code blocks."
)

def build_user_prompt(categories: list[str], count: int) -> str:
    cats = "|".join(categories)
    return f"""Generate {count} Sinhala health tips for YouTube Shorts for these categories: {", ".join(categories)}

CRITICAL LANGUAGE RULES — follow exactly:
- Use CASUAL everyday Sinhala, like talking to a friend. NOT formal or textbook Sinhala.
- Use "ඔයා" (not "ඔබ"), "ඔයාගේ" (not "ඔබගේ")
- Use colloquial verb forms: "දන්නවද", "හිතෙනවා", "වෙනවා", "කරන්න" (not formal "දැනුවත් ද", "ඇත", "කළ යුතුයි")
- Use simple everyday words: "මොළේ" or "මොළය" (NOT "මස්තිෂ්කය"), "ඇඟ" (NOT "ශරීරය"), "රෑ" (NOT "රාත්‍රිය"), "හිත" (NOT "මනස")
- Numbers → Sinhala words (7 → හත, 75% → සියයට හැත්තෑ පහ)
- Scientific terms → phonetic Sinhala (cortisol → කෝටිසෝල්, dopamine → ඩොපමීන්)
- NO English words, NO numerals
- Tip: 24-28 words, start with a hook/surprising fact, explain the WHY simply

GOOD example (use this style):
"ඔයා දන්නවද ඔයාගේ මොළයෙන් සියයට හැත්තෑ පහක්ම වතුර කියලා? වතුර ටිකක් අඩුවුණත් අවධානය නැතිවෙලා ලේසියෙන් මහන්සි දැනෙන්නෙ ඒකයි. දවස පුරා පොඩ්ඩ පොඩ්ඩ වතුර බොන්න අමතක කරන්න එපා."

BAD example (avoid this style):
"ඔබගේ මස්තිෂ්කය ජලය මගින් සෑදී ඇති නිසා ජලය ප්‍රමාණවත් ලෙස පරිභෝජනය කළ යුතුයි."

Output a JSON array only, no explanation:
[
  {{
    "id": "category-keyword",
    "title": "Short casual Sinhala title (5-8 words, question or exclamation)",
    "highlight": "ONE key concept word from title to show in orange",
    "category": "one of: {cats}",
    "tip": "Casual conversational Sinhala, 24-28 words, no English, no numerals",
    "hashtags": ["#qualitylife", "#සෞඛ්‍යය", "#area6fitness", "#relevant"]
  }}
]"""


def call_gemini(categories: list[str], count: int) -> list[dict]:
    """Call Gemini Flash to generate tip JSON."""
    print(f"[Gemini] Generating {count} tips for: {', '.join(categories)}")

    prompt = build_user_prompt(categories, count)

    # Load API key from .env or environment
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        env_file = REPO_DIR / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("GEMINI_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break

    if not api_key:
        print("ERROR: GEMINI_API_KEY not set. Add to .env or environment.", file=sys.stderr)
        sys.exit(1)

    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.9,
            ),
            contents=prompt,
        )
        raw = response.text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
            raw = raw.rsplit("```", 1)[0].strip()
        tips = json.loads(raw)
        print(f"[Gemini] Generated {len(tips)} tips")
        return tips
    except Exception as e:
        print(f"ERROR calling Gemini: {e}", file=sys.stderr)
        sys.exit(1)


def _unused_anthropic_fallback(categories: list[str], count: int) -> list[dict]:
    """Unused fallback kept for reference."""
    prompt = build_user_prompt(categories, count)
    try:
        import anthropic
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
            raw = raw.rsplit("```", 1)[0].strip()
        return json.loads(raw)
    except ImportError:
        pass

    print("ERROR: Could not call Claude Haiku. Install anthropic SDK or use claude CLI.", file=sys.stderr)
    sys.exit(1)


def save_tips(tips: list[dict]) -> list[Path]:
    TIPS_DIR.mkdir(parents=True, exist_ok=True)
    saved = []
    for tip in tips:
        tip_id = tip.get("id", f"tip-{len(saved)}")
        path = TIPS_DIR / f"{tip_id}.json"
        path.write_text(json.dumps(tip, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [Saved] {path.name}")
        saved.append(path)
    return saved


def generate_videos(tip_paths: list[Path], outdir: Path) -> list[Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    generated = []
    for tip_path in tip_paths:
        tip = json.loads(tip_path.read_text())
        out_mp4 = outdir / f"{tip['id']}.mp4"
        print(f"\n[Video] Generating: {tip['title']}")
        result = subprocess.run(
            [sys.executable, str(REPO_DIR / "shorts_gen.py"),
             "--tip", str(tip_path), "--output", str(out_mp4)],
            cwd=str(REPO_DIR)
        )
        if result.returncode == 0:
            generated.append(out_mp4)
        else:
            print(f"  [ERROR] Failed: {tip_path.name}", file=sys.stderr)
    return generated


def push_to_github(video_paths: list[Path], tip_paths: list[Path]) -> None:
    samples_dir = REPO_DIR / "samples"
    samples_dir.mkdir(exist_ok=True)
    for mp4 in video_paths:
        dest = samples_dir / mp4.name
        subprocess.run(["cp", str(mp4), str(dest)])

    os.chdir(REPO_DIR)
    subprocess.run(["git", "add", "content/tips/"])
    subprocess.run(["git", "add", "-f"] + [str(samples_dir / mp4.name) for mp4 in video_paths])
    count = len(video_paths)
    subprocess.run(["git", "commit", "-m", f"batch: {count} new health tip shorts"])
    result = subprocess.run(["git", "push"], capture_output=True, text=True)
    if result.returncode == 0:
        print(f"\n[GitHub] Pushed {count} videos to samples/")
    else:
        print(f"[GitHub] Push failed: {result.stderr}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Full Area6 health shorts pipeline")
    parser.add_argument("--categories", required=True,
                        help="Comma-separated categories e.g. hydration,sleep,exercise")
    parser.add_argument("--count", type=int, default=3,
                        help="Number of tips to generate (default: 3)")
    parser.add_argument("--no-push", action="store_true",
                        help="Skip GitHub push")
    parser.add_argument("--tips-only", action="store_true",
                        help="Only generate tip JSONs, skip video rendering")
    args = parser.parse_args()

    categories = [c.strip() for c in args.categories.split(",")]
    outdir = REPO_DIR / "output"

    # Step 1: Generate tips via Haiku
    tips = call_gemini(categories, args.count)
    print(f"\n[Haiku] Generated {len(tips)} tips")

    # Step 2: Save JSON files
    tip_paths = save_tips(tips)

    if args.tips_only:
        print("\nDone (tips only). Run generate_all.py to render videos.")
        return

    # Step 3: Render videos
    video_paths = generate_videos(tip_paths, outdir)
    print(f"\n[Done] {len(video_paths)}/{len(tips)} videos rendered to {outdir}/")

    # Step 4: Push to GitHub
    if not args.no_push and video_paths:
        push_to_github(video_paths, tip_paths)


if __name__ == "__main__":
    main()
