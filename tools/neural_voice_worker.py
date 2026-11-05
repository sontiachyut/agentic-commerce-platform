"""Isolated persistent local speech process. JSON-lines in/out; no app credentials."""

import base64
import contextlib
import io
import json
import sys
import time
import wave
from pathlib import Path


def main():
    model_path = Path(sys.argv[1]).resolve()
    with contextlib.redirect_stdout(sys.stderr):
        import mlx.core as mx
        import numpy as np
        from mlx_audio.tts.utils import load_model

        model = load_model(str(model_path))
    for line in sys.stdin:
        started = time.monotonic()
        try:
            body = json.loads(line)
            text, voice = body["text"], body.get("voice", "Ryan")
            if (
                not isinstance(text, str)
                or not 1 <= len(text) <= 1600
                or voice not in {"Ryan", "Aiden"}
            ):
                raise ValueError("Invalid bounded speech request")
            with contextlib.redirect_stdout(sys.stderr):
                mx.random.seed(42)
                chunks = list(
                    model.generate_custom_voice(
                        text=text,
                        speaker=voice,
                        language="English",
                        temperature=0.7,
                        max_tokens=2048,
                        verbose=False,
                    )
                )
                samples = np.concatenate([np.array(c.audio) for c in chunks]).reshape(-1)
                samples = (np.clip(samples, -1, 1) * 32767).astype("<i2")
                buffer = io.BytesIO()
                with wave.open(buffer, "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(model.sample_rate)
                    wav.writeframes(samples.tobytes())
            print(
                json.dumps(
                    {
                        "audio": base64.b64encode(buffer.getvalue()).decode(),
                        "sample_rate": model.sample_rate,
                        "duration_seconds": len(samples) / model.sample_rate,
                        "elapsed_seconds": round(time.monotonic() - started, 3),
                        "voice": voice,
                        "engine": "qwen3-tts-0.6b-8bit-mlx",
                    }
                ),
                flush=True,
            )
        except Exception as exc:
            print(json.dumps({"error": type(exc).__name__}), flush=True)


if __name__ == "__main__":
    main()
