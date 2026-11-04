"""Mix narration with a genuine Playwright workflow recording; keep source evidence."""

import argparse
import json
import subprocess
from pathlib import Path


def timestamp(seconds):
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3600000)
    minutes, milliseconds = divmod(milliseconds, 60000)
    secs, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{milliseconds:03}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    manifest = json.loads((args.directory / "recording.json").read_text())
    if not manifest.get("source_video"):
        raise SystemExit("The workflow did not complete; no client video was rendered.")
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-y",
        "-i",
        manifest["source_video"],
    ]
    tracks = [(s["path"], s["start"]) for s in manifest["scenes"]]
    tracks.append((manifest["voice_audio"], manifest["voice_start"]))
    tracks.extend((s["path"], s["start"]) for s in manifest.get("spoken_updates", []))
    filters, labels = [], []
    for index, (path, start) in enumerate(tracks, 1):
        command += ["-i", path]
        label = f"a{index}"
        filters.append(f"[{index}:a]adelay={round(start * 1000)}:all=1[{label}]")
        labels.append(f"[{label}]")
    filters.append(
        "".join(labels)
        + f"amix=inputs={len(labels)}:normalize=0:dropout_transition=0,alimiter=limit=0.95[mix]"
    )
    target = args.directory / "asterfield-family-pickup.mp4"
    command += [
        "-filter_complex",
        ";".join(filters),
        "-map",
        "0:v:0",
        "-map",
        "[mix]",
        "-c:v",
        "libx264",
        "-crf",
        "21",
        "-preset",
        "fast",
        "-pix_fmt",
        "yuv420p",
        "-r",
        "25",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        "-shortest",
        str(target),
    ]
    subprocess.run(command, check=True)
    subtitles = []
    for scene in manifest["scenes"]:
        # Short phrases are easier to read than one paragraph-long subtitle.
        words = scene["text"].split()
        chunks = [" ".join(words[i : i + 12]) for i in range(0, len(words), 12)]
        duration = scene["duration"] / len(chunks)
        for index, text in enumerate(chunks):
            start = scene["start"] + index * duration
            subtitles.append((start, start + duration, text))
    for spoken in manifest.get("spoken_updates", []):
        subtitles.append(
            (spoken["start"], spoken["start"] + spoken["duration"], "Assistant: " + spoken["text"])
        )
    if manifest["voice_start"] is not None:
        start = manifest["voice_start"]
        subtitles.append(
            (
                start,
                start + 8,
                "Alex: Order the regular medicines for my dad, mom, sister and myself from the nearest pharmacy to home. You can pay up to $50.",
            )
        )
    srt = (
        "\n\n".join(
            f"{index}\n{timestamp(start)} --> {timestamp(end)}\n{text}"
            for index, (start, end, text) in enumerate(sorted(subtitles), 1)
        )
        + "\n"
    )
    (args.directory / "asterfield-family-pickup.srt").write_text(srt)
    print(
        json.dumps(
            {
                "video": str(target),
                "captions": str(args.directory / "asterfield-family-pickup.srt"),
                "scenes": len(manifest["scenes"]),
            }
        )
    )


if __name__ == "__main__":
    main()
