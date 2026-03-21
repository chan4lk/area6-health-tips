# Piper TTS Model — Sinhala (si_LK)

This directory holds the Piper TTS voice model for Sinhala narration.

## Required files

Place both of the following files in this `piper/` directory:

| File | Purpose |
|------|---------|
| `si_LK-sinhala-medium.onnx` | ONNX model weights |
| `si_LK-sinhala-medium.onnx.json` | Model config (speaker info, sample rate, etc.) |

## Download

1. Go to the [Piper releases page](https://github.com/rhasspy/piper/releases)
   or the [Hugging Face model hub](https://huggingface.co/rhasspy/piper-voices).

2. Find the `si_LK` (Sinhala, Sri Lanka) voice — look for `sinhala-medium`.

3. Download both the `.onnx` and `.onnx.json` files.

4. Place them here:
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
