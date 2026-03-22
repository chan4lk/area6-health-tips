---
name: area6-health-shorts
description: Generate Area6 / qualitylife.lk branded YouTube Shorts in Sinhala. Calls Claude Haiku to generate health tip scripts, then runs the Piper TTS + FFmpeg pipeline to produce 9:16 vertical MP4 videos. Use when asked to generate health tip videos, Sinhala shorts, Area6 content, or run the health tips pipeline. Triggers on phrases like "generate health tips", "create shorts", "run the pipeline", "make videos for area6", "new batch of tips".
---

# Area6 Health Shorts Pipeline

Generates branded YouTube Shorts for Area6 / qualitylife.lk.

## Pipeline repo
`/home/openclaw/Projects/area6-health-tips`

## Full pipeline (one command)
```bash
cd /home/openclaw/Projects/area6-health-tips
python3 scripts/generate_batch.py --categories "hydration,sleep,exercise" --count 3
```
This calls Haiku, writes JSONs to `content/tips/`, generates all MP4s to `output/`, pushes samples to GitHub.

## Step by step

### 1. Generate tip scripts via Gemini 2.5 Flash
```bash
python3 scripts/generate_batch.py --categories "hydration,sleep" --count 5 --tips-only
# Writes JSON files to content/tips/
```
Requires `GEMINI_API_KEY` in `/home/openclaw/Projects/area6-health-tips/.env`

### 2. Generate videos from existing JSONs
```bash
python3 generate_all.py
# Outputs MP4s to output/
```

### 3. Generate a single tip video
```bash
python3 shorts_gen.py --tip content/tips/hydration-brain-power.json --output output/test.mp4
```

### 4. Push samples to GitHub
```bash
cp output/*.mp4 samples/
git add -f samples/*.mp4 && git add content/tips/ && git commit -m "batch: new health tip shorts" && git push
```

## Tip JSON format
```json
{
  "id": "category-keyword",
  "title": "Short Sinhala title (5-8 words)",
  "highlight": "ONE key word from title to show in orange",
  "category": "hydration|sleep|exercise|nutrition|mental|posture|habits|recovery|breathing|gut-health",
  "tip": "Sinhala narration, 24-28 words, NO English words or numerals",
  "hashtags": ["#qualitylife", "#සෞඛ්‍යය", "#area6fitness"]
}
```

## Prerequisites
- Piper model: `piper/si_LK-sinhala-medium.onnx` (see piper/README.md to download)
- Python: `pip install piper-tts Pillow numpy`
- System: `ffmpeg`, `fonts-noto-core`

## See references/haiku-prompt.md for the Haiku content generation prompt.
