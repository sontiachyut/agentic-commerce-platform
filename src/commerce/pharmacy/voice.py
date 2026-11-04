"""Bounded local-only WAV recognition; audio is temporary and never sent to a speech API."""

import io
import os
import subprocess
import tempfile
import time
import wave
from pathlib import Path

from commerce.domain import DomainError


class VoiceRecognizer:
    def __init__(self, settings):
        self.settings = settings

    def available(self):
        return (
            self.settings.voice_enabled
            and Path(self.settings.voice_executable).is_file()
            and Path(self.settings.voice_model).is_file()
        )

    def transcribe(self, audio):
        if not self.available():
            raise DomainError(
                "VOICE_UNAVAILABLE",
                "Local voice recognition is not installed. You can type the same request.",
                503,
            )
        try:
            with wave.open(io.BytesIO(audio), "rb") as source:
                if (
                    source.getnchannels() != 1
                    or source.getsampwidth() != 2
                    or source.getframerate() != 16000
                    or not 8000 <= source.getnframes() <= 720000
                ):
                    raise ValueError("Unsupported audio format or duration")
                frames = source.readframes(source.getnframes())
                if len(frames) != source.getnframes() * 2:
                    raise ValueError("Incomplete recording")
        except (wave.Error, EOFError, ValueError) as exc:
            raise DomainError(
                "VOICE_FORMAT",
                "Use a mono 16 kHz PCM recording between half a second and 45 seconds.",
                422,
            ) from exc
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="asterfield-voice-") as directory:
            path = Path(directory) / "request.wav"
            path.write_bytes(audio)
            output = Path(directory) / "transcript"
            try:
                result = subprocess.run(
                    [
                        str(Path(self.settings.voice_executable).resolve()),
                        "-m",
                        str(Path(self.settings.voice_model).resolve()),
                        "-f",
                        str(path),
                        "-l",
                        "en",
                        "-t",
                        "4",
                        "-nt",
                        "-np",
                        "-otxt",
                        "-of",
                        str(output),
                    ],
                    cwd=directory,
                    capture_output=True,
                    timeout=45,
                    check=False,
                    env={"PATH": os.defpath, "LANG": "en_US.UTF-8"},
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise DomainError(
                    "VOICE_UNAVAILABLE",
                    "The local recognizer did not finish. Please try a shorter request or type it.",
                    503,
                ) from exc
            transcript = output.with_suffix(".txt")
            if result.returncode != 0 or not transcript.is_file():
                raise DomainError(
                    "VOICE_UNAVAILABLE",
                    "Voice recognition did not finish. Please type your request.",
                    503,
                )
            text = transcript.read_text().strip()
            if not text or len(text) > 2000 or "[BLANK_AUDIO]" in text.upper():
                raise DomainError("VOICE_NOT_CLEAR", "I did not catch that. Please try again.", 422)
            return {
                "text": text,
                "engine": "whisper.cpp tiny.en · local",
                "elapsed_seconds": round(time.monotonic() - started, 3),
            }
