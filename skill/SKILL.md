---
name: area6-health-shorts
description: Generate and upload Area6 / qualitylife.lk branded YouTube Shorts with AI backgrounds and TTS narration. Supports Sinhala (Piper TTS) and English (Pocket TTS/Piper). Uses Imagen 4 for category-specific backgrounds, Gemini 2.5 Flash for tip scripts, and auto-uploads to YouTube @Area6_Content. Use when asked to generate health tip videos, create shorts, run the pipeline, upload to youtube, make videos for area6, generate new tips, or create a new batch.
---

# Area6 Health Shorts Pipeline

Generate and upload branded 9:16 vertical YouTube Shorts for Area6 / qualitylife.lk.

## Repo & channel
- Repo: `/home/chanclaw/.openclaw/workspace/area6-health-tips`
- YouTube: `@Area6_Content` (channel `UCRocfsBHK3AlK3TlUUX-HiQ`)
- OAuth: `/home/chanclaw/.openclaw/credentials/google-client.json` + `google-token.json`

## Quick start — full pipeline
```bash
cd /home/chanclaw/.openclaw/workspace/area6-health-tips
# 1. Generate tips (Gemini)
python3 scripts/generate_batch.py --categories "hydration,sleep" --count 5
# 2. Upload to YouTube
node scripts/youtube-upload.js --all
```

## Step-by-step commands

### Generate tip scripts (Gemini 2.5 Flash)
```bash
python3 scripts/generate_batch.py --categories "hydration,sleep" --count 5 --tips-only
```
See `references/gemini-prompt.md` for the prompt template.

### Generate AI backgrounds (Imagen 4)
```bash
python3 scripts/generate_backgrounds.py                    # all 10 categories
python3 scripts/generate_backgrounds.py exercise sleep     # specific
python3 scripts/generate_backgrounds.py --force            # regenerate
```
Saves to `branding/backgrounds/{category}.png`. Categories: breathing, exercise, sleep, nutrition, hydration, mental, posture, habits, recovery, gut-health.

### Render videos
```bash
python3 generate_all.py                  # all tips
python3 shorts_gen.py --tip content/tips/sleep-rest.json --output output/test.mp4  # single
```
Auto-selects category background → falls back to `branding/background.png`.

### Upload to YouTube
```bash
node scripts/youtube-upload.js --all                # private, skip already uploaded
node scripts/youtube-upload.js --all --public       # public
node scripts/youtube-upload.js --all --dry-run      # preview
```
Tracks in `scripts/upload-log.json`. Stops on rate limit. Cron: daily 4AM SL (job `dee7a47f`).

### Re-auth YouTube (token expires every 7 days in testing mode)
```bash
node /home/chanclaw/.openclaw/workspace/scripts/youtube-auth.js
```
Sign in with **Area6_Content Google account**.

## Tip JSON format
```json
{
  "id": "category-keyword",
  "title": "Short title (5-8 words)",
  "highlight": "ONE word to show in orange",
  "category": "hydration|sleep|exercise|nutrition|mental|posture|habits|recovery|breathing|gut-health",
  "tip": "Narration text, 24-28 words",
  "hashtags": ["#qualitylife", "#healthtips", "#area6fitness"]
}
```

## TTS voices
- **Sinhala**: `piper/si_LK-sinhala-medium.onnx` (custom trained, 1000 epochs)
- **English**: `piper/en_US-lessac-medium.onnx` or Pocket TTS (`pocket-tts generate --voice marius`)
- **Voice cloning** (Pocket TTS): needs HF token + terms at `huggingface.co/kyutai/pocket-tts`
- Chandima voice samples: `/home/chanclaw/shared-academy/month-*-videos/*-chandima-voice.mp4`

## Prerequisites
- Python: `piper-tts Pillow numpy google-genai pocket-tts`
- Node: `googleapis`
- Fonts: `NotoSans-Bold.ttf`, `NotoSansSinhala-Regular.ttf` in `~/.local/share/fonts/`
- FFmpeg, `GEMINI_API_KEY` in `.env`
