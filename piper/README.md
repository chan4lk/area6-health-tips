# Piper TTS Model — Sinhala (si_LK)

This directory holds the Piper TTS voice model for Sinhala narration.

## Required files

Place both of the following files in this `piper/` directory:

| File | Purpose |
|------|---------|
| `si_LK-sinhala-medium.onnx` | ONNX model weights |
| `si_LK-sinhala-medium.onnx.json` | Model config (speaker info, sample rate, etc.) |

## Download (Hugging Face)

This pipeline uses the custom Sinhala model trained on OpenSLR 30:
**https://huggingface.co/chan4lk/piper-tts-sinhala**

```bash
# Download model weights
wget -P piper/ \
  "https://huggingface.co/chan4lk/piper-tts-sinhala/resolve/main/si_LK-sinhala-medium.onnx"

# Download model config
wget -P piper/ \
  "https://huggingface.co/chan4lk/piper-tts-sinhala/resolve/main/si_LK-sinhala-medium.onnx.json"
```

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
