# Piper TTS Model — Sinhala (si_LK)

This directory holds the Piper TTS voice model for Sinhala narration.

## Required files

Place both of the following files in this `piper/` directory:

| File | Purpose |
|------|---------|
| `si_LK-sinhala-medium.onnx` | ONNX model weights |
| `si_LK-sinhala-medium.onnx.json` | Model config (speaker info, sample rate, etc.) |

## Download (Hugging Face)

Direct download links from the official [`rhasspy/piper-voices`](https://huggingface.co/rhasspy/piper-voices) repository:

```bash
# Download model weights
wget -P piper/ \
  "https://huggingface.co/rhasspy/piper-voices/resolve/main/si/si_LK/sinhala/medium/si_LK-sinhala-medium.onnx"

# Download model config
wget -P piper/ \
  "https://huggingface.co/rhasspy/piper-voices/resolve/main/si/si_LK/sinhala/medium/si_LK-sinhala-medium.onnx.json"
```

Or browse the model card:
- https://huggingface.co/rhasspy/piper-voices/tree/main/si/si_LK/sinhala/medium

Place them here:
```
piper/
├── si_LK-sinhala-medium.onnx
├── si_LK-sinhala-medium.onnx.json
└── README.md   ← you are here
```

## Verify

After placing the files, test synthesis:

```bash
echo "ආයුබෝවන්" | python -c "
import wave, sys
from piper import PiperVoice
voice = PiperVoice.load('piper/si_LK-sinhala-medium.onnx')
with wave.open('/tmp/test.wav', 'w') as wf:
    voice.synthesize(sys.stdin.read().strip(), wf)
print('Success: /tmp/test.wav')
"
```

## Notes

- The model uses a 22050 Hz sample rate; FFmpeg will resample to 44100 Hz for the final AAC audio track.
- `medium` quality is recommended — `low` sounds robotic, `high` is slower to synthesize.
- The `.onnx.json` file **must** accompany the `.onnx` file; Piper reads speaker and phoneme metadata from it.
