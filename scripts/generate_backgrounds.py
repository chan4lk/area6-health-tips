#!/usr/bin/env python3
"""
Generate unique AI backgrounds per category using Google Imagen 4.
Saves to branding/backgrounds/{category}.png
"""
import os
import sys
from pathlib import Path
from google import genai

ROOT = Path(__file__).parent.parent
ENV_PATH = ROOT / ".env"
BG_DIR = ROOT / "branding" / "backgrounds"

CATEGORY_PROMPTS = {
    "breathing": "Dark moody zen meditation scene, person silhouette breathing deeply, soft blue and orange ambient glow, misty atmosphere, 9:16 vertical portrait, cinematic, minimal, dark background",
    "exercise": "Dark gym interior silhouette, dumbbells and weights in shadow, dramatic orange amber side lighting, sweat particles in light beam, 9:16 vertical portrait, cinematic, premium fitness aesthetic",
    "sleep": "Dark bedroom scene, moonlight through window, soft purple and blue tones, peaceful night atmosphere, stars visible, 9:16 vertical portrait, cinematic minimal, calming",
    "nutrition": "Dark kitchen counter top-down, fresh colorful fruits and vegetables arranged artistically, dramatic warm lighting from above, 9:16 vertical portrait, moody food photography, dark background",
    "hydration": "Dark scene with crystal clear water splash, water droplets frozen in motion, blue and cyan glow, glass of water silhouette, 9:16 vertical portrait, cinematic, refreshing",
    "mental": "Dark meditation space, brain silhouette with neural connections glowing in orange, peaceful zen garden elements, 9:16 vertical portrait, cinematic, calming dark tones",
    "posture": "Dark scene showing human spine anatomy silhouette glowing in orange, ergonomic desk setup shadow, 9:16 vertical portrait, medical illustration style, dark moody",
    "habits": "Dark motivational scene, sunrise through window onto desk with journal and coffee, warm amber golden hour lighting, 9:16 vertical portrait, cinematic lifestyle",
    "recovery": "Dark gym recovery zone, foam roller and ice bath silhouette, cool blue and warm orange split lighting, 9:16 vertical portrait, cinematic, athletic recovery aesthetic",
    "gut-health": "Dark scientific scene, gut microbiome visualization with glowing bacteria in warm orange and green, abstract biological art, 9:16 vertical portrait, cinematic dark background",
}

def get_api_key():
    for line in ENV_PATH.read_text().splitlines():
        if line.startswith("GEMINI_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise ValueError("GEMINI_API_KEY not found in .env")

def generate_background(client, category, prompt, output_path):
    print(f"  🎨 Generating: {category}...")
    response = client.models.generate_images(
        model='imagen-4.0-fast-generate-001',
        prompt=prompt,
        config=genai.types.GenerateImagesConfig(
            number_of_images=1,
            aspect_ratio='9:16',
        )
    )
    if response.generated_images:
        img_bytes = response.generated_images[0].image.image_bytes
        output_path.write_bytes(img_bytes)
        print(f"  ✅ Saved: {output_path.name} ({len(img_bytes) // 1024}KB)")
        return True
    else:
        print(f"  ❌ No image generated for {category}")
        return False

def main():
    BG_DIR.mkdir(parents=True, exist_ok=True)
    
    categories = sys.argv[1:] if len(sys.argv) > 1 else list(CATEGORY_PROMPTS.keys())
    
    # Skip already generated unless --force
    force = "--force" in sys.argv
    if not force:
        categories = [c for c in categories if c in CATEGORY_PROMPTS and not (BG_DIR / f"{c}.png").exists()]
    else:
        categories = [c for c in categories if c in CATEGORY_PROMPTS]
    
    if not categories:
        print("✅ All category backgrounds already exist. Use --force to regenerate.")
        return
    
    print(f"🖼️  Generating {len(categories)} background(s)...\n")
    
    client = genai.Client(api_key=get_api_key())
    
    success = 0
    for cat in categories:
        try:
            if generate_background(client, cat, CATEGORY_PROMPTS[cat], BG_DIR / f"{cat}.png"):
                success += 1
        except Exception as e:
            print(f"  ❌ Error for {cat}: {e}")
    
    print(f"\n🎉 Done: {success}/{len(categories)} backgrounds generated")
    print(f"📁 Location: {BG_DIR}/")

if __name__ == "__main__":
    main()
