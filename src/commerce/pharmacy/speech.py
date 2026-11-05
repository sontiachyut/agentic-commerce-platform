"""Natural local speech for backend-owned statuses, never arbitrary LLM prose."""

import atexit
import base64
import json
import os
import queue
import subprocess
import threading
from collections import OrderedDict
from pathlib import Path

from commerce.domain import DomainError


def status_sentence(detail):
    state, order = detail["state"], detail.get("order")
    if state == "ORDERED" and order:
        amount = f"{order['amount_minor'] // 100} dollars and {order['amount_minor'] % 100} cents"
        return (
            f"Your family order is accepted at Asterfield {order['facility']['name']}, "
            f"{order['facility']['address']}. The total is {amount}. "
            "The pharmacy will let you know when it is ready for pickup."
        )
    if state == "READY_FOR_PICKUP" and order:
        amount = f"{order['amount_minor'] // 100} dollars and {order['amount_minor'] % 100} cents"
        return f"Your family order is ready for pickup at {order['facility']['name']}. Payment of {amount} is confirmed."
    if state in {
        "BLOCKED",
        "NEEDS_INPUT",
        "BUDGET_EXCEEDED",
        "AWAITING_APPROVAL",
        "MODEL_UNAVAILABLE",
        "PICKED_UP",
        "CANCELED",
        "NEEDS_REVIEW",
    }:
        return detail["message"]
    raise DomainError("SPEECH_PENDING", "There is no confirmed status to speak yet.", 409)


class NeuralSpeaker:
    def __init__(self, settings):
        self.settings = settings
        self.process = None
        self.responses = queue.Queue()
        self.lock = threading.Lock()
        self.cache = OrderedDict()
        atexit.register(self.close)

    def available(self):
        return (
            self.settings.voice_enabled
            and Path(self.settings.tts_python).is_file()
            and (Path(self.settings.tts_model) / "model.safetensors").is_file()
        )

    def _start(self):
        root = Path(__file__).resolve().parents[3]
        self.responses = queue.Queue()
        self.process = subprocess.Popen(
            [
                str(Path(self.settings.tts_python).absolute()),
                str(root / "tools/neural_voice_worker.py"),
                str(Path(self.settings.tts_model).resolve()),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            env={
                "PATH": os.defpath,
                "LANG": "en_US.UTF-8",
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
                "TOKENIZERS_PARALLELISM": "false",
            },
        )
        stream, responses = self.process.stdout, self.responses

        def read():
            for line in stream:
                responses.put(line)
            responses.put(None)

        threading.Thread(target=read, name="local-neural-speech", daemon=True).start()

    def speak(self, text, voice="Ryan"):
        if not self.available():
            raise DomainError(
                "SPEECH_UNAVAILABLE",
                "Natural voice is not installed. Your written status remains available.",
                503,
            )
        if not self.lock.acquire(timeout=1):
            raise DomainError(
                "SPEECH_BUSY", "Natural voice is busy. Your written status remains available.", 429
            )
        try:
            key = (text, voice)
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
            if not self.process or self.process.poll() is not None:
                self.close()
                self._start()
            try:
                self.process.stdin.write(json.dumps({"text": text, "voice": voice}) + "\n")
                self.process.stdin.flush()
                line = self.responses.get(timeout=90)
                result = json.loads(line) if line else {}
                audio = base64.b64decode(result.get("audio", ""), validate=True)
                if result.get("error") or not audio.startswith(b"RIFF") or len(audio) > 5000000:
                    raise ValueError("Invalid speech output")
            except (OSError, ValueError, queue.Empty):
                self.close()
                raise DomainError(
                    "SPEECH_UNAVAILABLE",
                    "Natural voice could not finish. Your written status remains available.",
                    503,
                ) from None
            result["text"] = text
            self.cache[key] = result
            while len(self.cache) > 8:
                self.cache.popitem(last=False)
            return result
        finally:
            self.lock.release()

    def close(self):
        process, self.process = self.process, None
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        if process:
            for stream in (process.stdin, process.stdout):
                if stream:
                    stream.close()
