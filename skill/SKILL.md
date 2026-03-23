---
name: area6-health-shorts
description: Generate and upload Area6 / qualitylife.lk branded YouTube Shorts. Supports Sinhala (Piper TTS) and English (Pocket TTS with voice cloning). Uses Imagen 4 AI-generated backgrounds per category, Gemini 2.5 Flash for tip scripts, and auto-uploads to YouTube @Area6_Content. Triggers on phrases like "generate health tips", "create shorts", "run the pipeline", "make videos for area6", "upload to youtube", "new batch of tips".
---

# Area6 Health Shorts Pipeline

Generates and uploads branded YouTube Shorts for Area6 / qualitylife.lk.

## Pipeline repo
`/home/chanclaw/.openclaw/workspace/area6-health-tips`

## YouTube channel
- **@Area6_Content**: <https://www.youtube.com/@Area6_Content>
- Channel ID: `UCRocfsBHK3AlK3TlUUX-HiQ`
- OAuth credentials: `/home/chanclaw/.openclaw/credentials/google-client.json` + `google-token.json`
- Upload cron: daily at 4AM SL (job `dee7a47f`), reports to Discord #gym-tips

## Full pipeline (one command)
```bash
cd /home/chanclaw/.openclaw/workspace/area6-health-tips
python3 scripts/generate_batch.py --categories "hydration,sleep,exercise" --count 3
```
This calls Gemini 2.5 Flash, writes JSONs to `content/tips/`, generates all MP4s to `output/`.

## Step by step

### 1. Generate tip scripts via Gemini 2.5 Flash
```bash
python3 scripts/generate_batch.py --categories "hydration,sleep" --count 5 --tips-only
# Writes JSON files to content/tips/
```
Requires `GEMINI_API_KEY` in `.env`

### 2. Generate AI backgrounds per category (Imagen 4)
```bash
python3 scripts/generate_backgrounds.py                    # all categories
python3 scripts/generate_backgrounds.py exercise sleep     # specific categories
python3 scripts/generate_backgrounds.py --force            # regenerate all
```
Saves to `branding/backgrounds/{category}.png`. Each of the 10 categories gets a unique AI-generated background.

### 3. Generate videos from existing JSONs
```bash
python3 generate_all.py
# Outputs MP4s to output/
```
Automatically picks category-specific background, falls back to `branding/background.png`.

### 4. Generate a single tip video
```bash
python3 shorts_gen.py --tip content/tips/hydration-brain-power.json --output output/test.mp4
```

### 5. Upload to YouTube (@Area6_Content)
```bash
node scripts/youtube-upload.js --all                # upload all (private, skip already uploaded)
node scripts/youtube-upload.js --all --public       # upload as public
node scripts/youtube-upload.js output/sleep.mp4     # upload single video
node scripts/youtube-upload.js --all --dry-run      # preview what would upload
```
- Tracks uploads in `scripts/upload-log.json` (dedup)
- Stops on YouTube rate limit automatically
- OAuth token may need refresh every 7 days (Google testing mode)

### 6. Re-auth YouTube (when token expires)
```bash
node scripts/youtube-auth.js
# Or use the workspace-level auth script:
node /home/chanclaw/.openclaw/workspace/scripts/youtube-auth.js
```
Sign in with the **Area6_Content Google account**, paste redirect URL back.

## Tip JSON format
```json
{
  "id": "category-keyword",
  "title": "Short title (5-8 words, Sinhala or English)",
  "highlight": "ONE key word from title to show in orange",
  "category": "hydration|sleep|exercise|nutrition|mental|posture|habits|recovery|breathing|gut-health",
  "tip": "Narration text, 24-28 words",
  "hashtags": ["#qualitylife", "#healthtips", "#area6fitness"]
}
```

## Categories & AI backgrounds
Each category has a unique Imagen 4 generated background in `branding/backgrounds/`:
- `breathing` — Zen meditation, blue/orange glow
- `exercise` — Gym interior, orange amber lighting
- `sleep` — Moonlit bedroom, purple/blue tones
- `nutrition` — Dark food photography, warm lighting
- `hydration` — Water splash, blue/cyan glow
- `mental` — Brain neural connections, zen elements
- `posture` — Spine anatomy silhouette
- `habits` — Sunrise lifestyle scene
- `recovery` — Gym recovery zone, split lighting
- `gut-health` — Microbiome visualization

## TTS Voices
- **Sinhala**: Piper TTS (`piper/si_LK-sinhala-medium.onnx`) — custom trained 1000 epochs
- **English**: Piper lessac (`piper/en_US-lessac-medium.onnx`) or Pocket TTS (voice cloning capable)
- **Pocket TTS voices**: alba, marius, javert, jean, fantine, cosette, eponine, azelma
- **Voice cloning**: Requires HuggingFace token + terms acceptance at `huggingface.co/kyutai/pocket-tts`
- **Chandima voice samples**: `/home/chanclaw/shared-academy/month-1-videos/*-chandima-voice.mp4`

## Prerequisites
- Piper model: `piper/si_LK-sinhala-medium.onnx`
- English Piper: `piper/en_US-lessac-medium.onnx`
- Python: `pip install piper-tts Pillow numpy google-genai pocket-tts`
- Node: `googleapis` (for YouTube upload)
- System: `ffmpeg`, Noto Sans + Noto Sans Sinhala fonts in `~/.local/share/fonts/`
- API keys: `GEMINI_API_KEY` in `.env`, Google OAuth in credentials

## Cron jobs
- **Area6 YouTube Upload**: daily 4AM SL, uploads ~5-10 videos/day until all done (job `dee7a47f`)
