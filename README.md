# area6-health-tips

YouTube Shorts pipeline for **Area6 / [qualitylife.lk](https://qualitylife.lk)** — converts Sinhala health tip narrations into branded, 9:16 vertical short-form videos (≤10 seconds).

> Area6 branding assets (logo, colors) will be dropped in later. The pipeline currently uses `qualitylife.lk` as placeholder brand text.

---

## Overview

```
AUDIO-NARRATIVE-SI.md
        │
        ▼
extract_shorts.py  →  shorts_plan.json  (slide snippets, durations)
        │
        ▼
shorts_gen.py  →  slide_001.mp4, slide_002.mp4, ...
                  (Piper TTS audio + branded video overlay)
```

Each output video is:
- **1080 × 1920** (9:16 vertical, YouTube Shorts format)
- **≤ 10 seconds** (auto-truncated if narration is too long)
- **30 fps, H.264 / AAC**, faststart for web streaming
- Dark gradient background with brand text overlay

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

Download the Sinhala voice model into `./piper/` — two files needed:

```bash
wget -P piper/ \
  "https://huggingface.co/rhasspy/piper-voices/resolve/main/si/si_LK/sinhala/medium/si_LK-sinhala-medium.onnx"

wget -P piper/ \
  "https://huggingface.co/rhasspy/piper-voices/resolve/main/si/si_LK/sinhala/medium/si_LK-sinhala-medium.onnx.json"
```

Model source: https://huggingface.co/rhasspy/piper-voices/tree/main/si/si_LK/sinhala/medium

---

## Usage

### Generate a Short from inline text

```bash
python shorts_gen.py \
  --text "ශරීරය සෞඛ්‍යමත්ව තබා ගැනීමට දිනපතා ව්‍යායාම කිරීම අත්‍යවශ්‍යයි." \
  --title "Daily Exercise" \
  --output tip.mp4
```

### Generate a Short from a specific slide

```bash
python shorts_gen.py \
  --narrative path/to/AUDIO-NARRATIVE-SI.md \
  --slide 3 \
  --output slide_03.mp4
```

### Batch generate all slides

```bash
python shorts_gen.py \
  --narrative path/to/AUDIO-NARRATIVE-SI.md \
  --all \
  --outdir ./shorts/
```

---

## Batch extraction (planning step)

Inspect which snippets will be extracted and their estimated durations before rendering:

```bash
python extract_shorts.py path/to/AUDIO-NARRATIVE-SI.md --output shorts_plan.json
```

Output JSON:
```json
[
  {
    "slide_number": 1,
    "title": "Introduction",
    "text": "ශරීරය...",
    "estimated_duration": 7.3,
    "word_count": 22,
    "was_truncated": false
  }
]
```

---

## Project structure

```
area6-health-tips/
├── shorts_gen.py          # Main pipeline: text → TTS → MP4
├── extract_shorts.py      # Extracts short snippets from narrative MD
├── requirements.txt       # piper-tts, numpy
├── piper/
│   ├── README.md          # Model download instructions (HuggingFace URLs)
│   ├── si_LK-sinhala-medium.onnx        # (download separately)
│   └── si_LK-sinhala-medium.onnx.json   # (download separately)
└── README.md
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `piper-tts not installed` | `pip install piper-tts` |
| `Piper model not found` | Run the `wget` commands above to download to `./piper/` |
| Subtitle text shows boxes/tofu | `sudo apt install fonts-noto-core && fc-cache -fv` |
| FFmpeg not found | `sudo apt install ffmpeg` |
| Video has no audio | Check TTS step: run `piper_to_speech.py` in isolation first |
