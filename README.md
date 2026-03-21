# area6-health-tips

YouTube Shorts pipeline for **Area6 / [qualitylife.lk](https://qualitylife.lk)** — generates branded 9:16 vertical Sinhala health tip videos (≤10 seconds) with Piper TTS narration.

---

## Overview

```
content/tips/*.json   (one JSON file per health tip)
        │
        ▼
shorts_gen.py  →  Piper TTS (Sinhala audio) + FFmpeg (branded video)
        │
        ▼
output/hydration.mp4, output/sleep.mp4, ...
```

Each output video is:
- **1080 × 1920** (9:16 vertical, YouTube Shorts format)
- **≤ 10 seconds** (auto-truncated if narration is too long)
- **30 fps, H.264 / AAC**, faststart for web streaming
- Dark gradient background with `qualitylife.lk` brand overlay

---

## Prerequisites

### 1. System dependencies

```bash
# FFmpeg (video rendering)
sudo apt install ffmpeg

# Sinhala font (required for subtitle text rendering)
sudo apt install fonts-noto-core
```

Verify the font is available:
```bash
fc-list | grep -i sinhala
```

### 2. Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Piper TTS model

Download the custom Sinhala model (trained on OpenSLR 30) into `./piper/`:

```bash
wget -P piper/ \
  "https://huggingface.co/chan4lk/piper-tts-sinhala/resolve/main/si_LK-sinhala-medium.onnx"

wget -P piper/ \
  "https://huggingface.co/chan4lk/piper-tts-sinhala/resolve/main/si_LK-sinhala-medium.onnx.json"
```

Model: https://huggingface.co/chan4lk/piper-tts-sinhala

---

## Usage

### Generate one Short from a tip file

```bash
python3 shorts_gen.py --tip content/tips/hydration.json --output output/hydration.mp4
```

### Generate all Shorts at once

```bash
python3 shorts_gen.py --all --outdir output/
# or equivalently:
python3 generate_all.py
```

---

## Adding new tips

Create a new file in `content/tips/` following this schema:

```json
{
  "id": "unique-slug",
  "title": "Short catchy title in Sinhala (shown on screen)",
  "category": "hydration|sleep|exercise|nutrition|mental|posture|habits",
  "tip": "The actual narration — professional but friendly tone. ~25-30 Sinhala words.",
  "hashtags": ["#qualitylife", "#සෞඛ්‍යය", "..."]
}
```

Then run:
```bash
python3 shorts_gen.py --tip content/tips/your-tip.json --output output/your-tip.mp4
```

---

## Project structure

```
area6-health-tips/
├── shorts_gen.py          # Main pipeline: tip JSON → TTS → MP4
├── generate_all.py        # Batch runner for all tips
├── requirements.txt       # piper-tts, numpy
├── content/
│   └── tips/              # One JSON file per health tip
│       ├── hydration.json
│       ├── sleep.json
│       ├── exercise.json
│       ├── nutrition.json
│       ├── mental.json
│       ├── posture.json
│       └── habits.json
├── piper/
│   ├── README.md                        # Model download instructions
│   ├── si_LK-sinhala-medium.onnx        # (download separately)
│   └── si_LK-sinhala-medium.onnx.json   # (download separately)
└── output/                # Generated MP4s (git-ignored)
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `piper-tts not installed` | `pip install piper-tts` |
| `Piper model not found` | Run the `wget` commands above to download to `./piper/` |
| Subtitle text shows boxes/tofu | `sudo apt install fonts-noto-core && fc-cache -fv` |
| FFmpeg not found | `sudo apt install ffmpeg` |
