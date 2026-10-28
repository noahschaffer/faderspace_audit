#!/usr/bin/env python3
"""Build the published copy of the audition page into docs/, for GitHub Pages.

    python3 build_site.py

docs/ holds the same page as the local copy, with lighter audio:

    index.html, app.js, style.css          copied as they are
    manifest.js                            the manifest, pointing at the files below
    audio/<experiment>/direction_<k>.mp3   a direction's clips, MP3-encoded and stored back to back
    .nojekyll                              tells GitHub Pages to serve the folder as it is

The WAVs are too heavy to publish (1.4 GB for musiccaps_trumpet), so each clip is re-encoded
(192 kbps by default, about 240 KB per 10 s clip). A direction's clips share one file: one request
per direction instead of ten, and 64 files in git instead of 640. The page cuts each clip back out
by byte range. Needs ffmpeg.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from build_manifest import HERE, index_assets, write_manifest

OUT = HERE / "docs"
PAGE_FILES = ("index.html", "app.js", "style.css")
MAX_SITE_BYTES = 1024**3  # GitHub Pages refuses to publish a bigger site


def clips_of(manifest):
    for experiment in manifest["experiments"]:
        for direction in experiment["directions"]:
            for side in ("neg", "pos"):
                for clip in direction[side]:
                    yield experiment, direction, clip


def encode(source, mp3, bitrate):
    mp3.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(source), "-c:a", "libmp3lame", "-b:a", bitrate, str(mp3)],
        check=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--assets", type=Path, default=HERE / "assets", help="folder of experiments (default: ./assets)")
    parser.add_argument("--bitrate", default="192k", help="MP3 bitrate (default: 192k)")
    args = parser.parse_args()
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is required (brew install ffmpeg)")

    manifest = index_assets(args.assets, HERE)
    start = time.perf_counter()
    shutil.rmtree(OUT / "audio", ignore_errors=True)

    with tempfile.TemporaryDirectory() as tmp:

        def mp3_of(direction, clip):
            return Path(tmp, direction["path"], clip["file"]).with_suffix(".mp3")

        with ThreadPoolExecutor() as pool:
            jobs = [
                pool.submit(encode, HERE / direction["path"] / clip["file"], mp3_of(direction, clip), args.bitrate)
                for _, direction, clip in clips_of(manifest)
            ]
            for job in jobs:
                job.result()  # surface the first ffmpeg failure

        for experiment in manifest["experiments"]:
            for direction in experiment["directions"]:
                bundle = bytearray()
                for clip in direction["neg"] + direction["pos"]:
                    data = mp3_of(direction, clip).read_bytes()
                    clip["bytes"] = [len(bundle), len(bundle) + len(data)]
                    bundle += data
                path = Path("audio", experiment["name"], f"direction_{direction['id']}.mp3")
                (OUT / path).parent.mkdir(parents=True, exist_ok=True)
                (OUT / path).write_bytes(bundle)
                direction["bundle"] = path.as_posix()
                del direction["path"]

    for name in PAGE_FILES:
        shutil.copy2(HERE / name, OUT / name)
    write_manifest(manifest, OUT / "manifest.js", "build_site.py")
    (OUT / ".nojekyll").touch()

    bundles = len(list((OUT / "audio").rglob("*.mp3")))
    size = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file())
    print(f"Wrote {OUT.name}/: the page + {bundles} audio files, {size / 1024**2:.0f} MB ({time.perf_counter() - start:.0f}s)")
    if size > MAX_SITE_BYTES:
        print("  Over GitHub Pages' 1 GB limit for a site; try a lower --bitrate", file=sys.stderr)


if __name__ == "__main__":
    main()
