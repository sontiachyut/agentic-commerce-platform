"""Provision a checksum-pinned, isolated Apple Silicon natural voice runtime."""

import hashlib
import json
import platform
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise SystemExit("This optional MLX profile currently targets Apple Silicon Macs.")
    lock = json.loads((ROOT / "docs/pharmacy/tts-runtime.lock.json").read_text())
    private = ROOT / ".local/voice"
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    environment = private / "tts-venv"
    if not environment.exists():
        subprocess.run(["uv", "venv", str(environment), "--python", "3.12"], check=True)
    subprocess.run(
        [
            "uv",
            "pip",
            "sync",
            "--python",
            str(environment / "bin/python"),
            str(ROOT / "tools/voice/requirements.lock"),
            "--require-hashes",
        ],
        check=True,
    )
    for item in lock["files"]:
        path = private / "tts-model" / item["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            temporary = path.with_suffix(path.suffix + ".download")
            with (
                urllib.request.urlopen(item["url"], timeout=90) as src,
                temporary.open("wb") as target,
            ):
                while chunk := src.read(1024 * 1024):
                    target.write(chunk)
            temporary.replace(path)
        hasher = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                hasher.update(chunk)
        if hasher.hexdigest() != item["sha256"] or path.stat().st_size != item["bytes"]:
            raise SystemExit("Natural voice file failed verification: " + item["path"])
    print(
        "Pinned Qwen3-TTS natural voice is ready. Inference stays local; no paid speech API or cloned voice."
    )


if __name__ == "__main__":
    main()
