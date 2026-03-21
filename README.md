# academy-shorts

YouTube Shorts pipeline for **BISTEC Hearts Academy** — converts Sinhala lesson narrations into branded, 9:16 vertical short-form videos (≤10 seconds).

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
                  (TTS audio + branded video overlay)
```

Each output video is:
- **1080 × 1920** (9:16 vertical, YouTube Shorts format)
- **≤ 10 seconds** (auto-truncated if narration is too long)
- **30 fps, H.264 / AAC**, faststart for web streaming
- Dark gradient background with BISTEC Hearts Academy branding

---

## Prerequisites

### 1. System dependencies

```bash
# FFmpeg (video rendering)
sudo apt install ffmpeg

# Sinhala font (required for subtitle text rendering)
sudo apt install fonts-noto-core
# or: fonts-noto  (larger package with all scripts)
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

Download the Sinhala voice model and place it in `./piper/`:

```
piper/
├── si_LK-sinhala-medium.onnx
└── si_LK-sinhala-medium.onnx.json
```

See [`piper/README.md`](piper/README.md) for download instructions.

---

## Usage

### Generate a single Short from inline text

```bash
python shorts_gen.py \
  --text "ආයුබෝවන්! BISTEC Hearts Academy වෙතින් සාදරයෙන් පිළිගනිමු." \
  --title "Welcome" \
  --output welcome.mp4
```

### Generate a Short from a specific slide

```bash
python shorts_gen.py \
  --narrative path/to/AUDIO-NARRATIVE-SI.md \
  --slide 3 \
  --output slide_03.mp4
```

### Generate Shorts for all slides

```bash
python shorts_gen.py \
  --narrative path/to/AUDIO-NARRATIVE-SI.md \
  --all \
  --outdir ./shorts/
```

Output files will be named `slide_001.mp4`, `slide_002.mp4`, etc.

---

## Batch extraction (planning step)

Before generating videos, inspect which snippets will be used and their estimated durations:

```bash
python extract_shorts.py path/to/AUDIO-NARRATIVE-SI.md --output shorts_plan.json
```

This produces a JSON file like:

```json
[
  {
    "slide_number": 1,
    "title": "Introduction to GSD",
    "text": "ගෝලීය ශිෂ්‍ය සංවර්ධනය යනු...",
    "estimated_duration": 7.3,
    "word_count": 22,
    "was_truncated": false
  },
  ...
]
```

Options:
```
--max-duration N    Override the 10-second cap (default: 10.0)
--print             Also print the plan to stdout
```

---

## Project structure

```
academy-shorts/
├── shorts_gen.py          # Main pipeline: text → TTS → MP4
├── extract_shorts.py      # Extracts short snippets from narrative MD
├── requirements.txt       # Python dependencies
├── piper/
│   ├── README.md          # Model download instructions
│   ├── si_LK-sinhala-medium.onnx        # (download separately)
│   └── si_LK-sinhala-medium.onnx.json   # (download separately)
└── README.md
```

---

## Sinhala font notes

FFmpeg's `drawtext` filter requires a font file that supports the Sinhala Unicode block (U+0D80–U+0DFF). The pipeline tries these paths in order:

1. `/usr/share/fonts/truetype/noto/NotoSansSinhala-Regular.ttf`
2. `/usr/share/fonts/noto/NotoSansSinhala-Regular.ttf`
3. Fallback to NotoSans or DejaVu (Latin only — Sinhala glyphs won't render)

Install the recommended font:
```bash
sudo apt install fonts-noto-core
fc-cache -fv
```

---

## Text duration estimation

The pipeline estimates speech rate at **3 words/second** for Sinhala. Text is auto-truncated to keep the video ≤10 seconds. The actual TTS output duration is used for the final video length.

To adjust the rate, edit `WORDS_PER_SECOND` in `shorts_gen.py` or `extract_shorts.py`.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `piper-tts not installed` | `pip install piper-tts` |
| `Piper model not found` | Download `.onnx` files to `./piper/` — see `piper/README.md` |
| Subtitle text shows boxes/tofu | Install `fonts-noto-core` and re-run |
| FFmpeg not found | `sudo apt install ffmpeg` |
| Video has no audio | Check that the WAV was synthesized correctly (run TTS step in isolation) |
