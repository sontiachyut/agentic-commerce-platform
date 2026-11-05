"""Generate disclosed neural narration locally using a supplied preset voice."""

import argparse
import base64
import json
from pathlib import Path

from commerce.config import Settings
from commerce.pharmacy.speech import NeuralSpeaker


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    narrator = NeuralSpeaker(Settings())
    results = []
    try:
        for key, text in json.loads((directory / "narration-input.json").read_text()):
            path = directory / (key + ".wav")
            result = narrator.speak(text)
            path.write_bytes(base64.b64decode(result["audio"]))
            results.append(
                {
                    "key": key,
                    "path": str(path),
                    "text": text,
                    "duration": result["duration_seconds"],
                    "generation_seconds": result["elapsed_seconds"],
                    "engine": result["engine"],
                    "voice": result["voice"],
                }
            )
            print("Natural narration ready:", key, flush=True)
    finally:
        narrator.close()
    (directory / "narration.json").write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
