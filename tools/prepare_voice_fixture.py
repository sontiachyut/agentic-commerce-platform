"""Create reproducible synthetic microphone audio on macOS for tests/demos."""

import base64
import json
import shutil
import subprocess
from pathlib import Path

from commerce.config import Settings
from commerce.pharmacy.speech import NeuralSpeaker

ROOT = Path(__file__).resolve().parents[1]
COMMAND = (
    "Order the regular medicines for my dad, mom, sister and myself from the nearest pharmacy to home. "
    "You can pay up to fifty dollars."
)


def main():
    if not shutil.which("ffmpeg"):
        raise SystemExit(
            "The synthetic test fixture requires local FFmpeg. Live microphone use does not."
        )
    directory = ROOT / ".local/voice"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    source = directory / "family-request.wav"
    speaker = NeuralSpeaker(Settings())
    try:
        result = speaker.speak(COMMAND, "Aiden")
        source.write_bytes(base64.b64decode(result["audio"]))
    finally:
        speaker.close()
    padded = directory / "family-request-padded.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-af",
            "adelay=600:all=1,apad=pad_dur=3",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(padded),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(padded),
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(directory / "fake-capture.wav"),
        ],
        check=True,
    )
    (directory / "synthetic-command.json").write_text(
        json.dumps(
            {
                "text": COMMAND,
                "source": "Qwen3-TTS supplied Aiden preset; synthesized command, not a hardware microphone recording",
            },
            indent=2,
        )
    )
    print("Synthetic microphone fixture prepared; all files stay under ignored .local/voice.")


if __name__ == "__main__":
    main()
