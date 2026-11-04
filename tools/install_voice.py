"""Provision the pinned local speech runtime. No model API key or auth-cache access."""

import hashlib
import json
import shutil
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest = json.loads((ROOT / "docs/pharmacy/voice-runtime.lock.json").read_text())
    private = ROOT / ".local/voice"
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    source = private / "whisper.cpp"
    if not source.exists():
        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--branch",
                manifest["version"],
                "https://github.com/ggml-org/whisper.cpp.git",
                str(source),
            ],
            check=True,
        )
    observed = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()
    if observed != manifest["revision"]:
        raise SystemExit("Speech source revision differs; existing directory was preserved.")
    if not shutil.which("cmake"):
        raise SystemExit("Install CMake and a C++ compiler first.")
    subprocess.run(
        [
            "cmake",
            "-S",
            str(source),
            "-B",
            str(source / "build"),
            "-DCMAKE_BUILD_TYPE=Release",
            "-DGGML_METAL=OFF",
            "-DWHISPER_BUILD_TESTS=OFF",
        ],
        check=True,
    )
    subprocess.run(
        ["cmake", "--build", str(source / "build"), "--target", "whisper-cli", "-j", "4"],
        check=True,
    )
    model = private / "ggml-tiny.en.bin"
    if not model.exists():
        temporary = private / "model.download"
        with (
            urllib.request.urlopen(manifest["model_url"], timeout=90) as response,
            temporary.open("wb") as target,
        ):
            while chunk := response.read(1024 * 1024):
                target.write(chunk)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != manifest["model_sha256"]:
            temporary.unlink()
            raise SystemExit("Model checksum mismatch")
        temporary.replace(model)
    if hashlib.sha256(model.read_bytes()).hexdigest() != manifest["model_sha256"]:
        raise SystemExit("Installed model checksum mismatch")
    print(
        "Pinned local speech runtime ready. Voice recordings remain temporary; no cloud speech service configured."
    )


if __name__ == "__main__":
    main()
