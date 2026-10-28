#!/usr/bin/env python3
"""Index the audio under assets/ into manifest.js for the audition page (index.html).

Expected layout:

    assets/<experiment>/direction_<k>/neg_<rank>_<key>_<value>[_<key>_<value>...].wav
    assets/<experiment>/direction_<k>/pos_<rank>_<key>_<value>[_<key>_<value>...].wav
    assets/<experiment>/prompts.txt                 (optional; or the folder's only .txt file)
    assets/<experiment>/.hydra/config.yaml          (optional, shown in the sidebar)

The prompt list has one prompt per line: line N (counting from 0) is shown on every clip
whose file name says prompt_N.

Re-run whenever experiments are added or changed:

    python3 build_manifest.py

Standard library only. The manifest is a JS file rather than JSON so the page also
works when index.html is opened straight from disk (file://), where browsers refuse
to fetch() local files.
"""

from __future__ import annotations

import argparse
import array
import json
import math
import operator
import os
import re
import sys
import time
import wave
from pathlib import Path

try:
    from math import sumprod
except ImportError:  # Python < 3.12

    def sumprod(a, b):
        return sum(map(operator.mul, a, b))


HERE = Path(__file__).resolve().parent
DIRECTION_RE = re.compile(r"direction_(\d+)")
CLIP_RE = re.compile(r"(neg|pos)_(\d+)(?:_(.*))?")
META_RE = re.compile(r"([A-Za-z]+)_(-?\d+(?:\.\d+)?)")
AUDIO_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".oga", ".m4a", ".aac", ".webm"}

BUCKETS = 200  # waveform resolution per clip
STRIDE = 4  # analyse every 4th frame: ~4x faster, visually identical
LEVELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
SAMPLE_TYPES = {2: ("h", 2**15), 4: ("i", 2**31)}  # bytes per sample -> (array typecode, full scale)


def number(text):
    return float(text) if "." in text else int(text)


def parse_clip(path):
    """'neg_0_prompt_10_variant_9.wav' -> ('neg', 0, {'prompt': 10, 'variant': 9})"""
    match = CLIP_RE.fullmatch(path.stem)
    if not match:
        return None
    side, rank, rest = match.groups()
    return side, int(rank), {k: number(v) for k, v in META_RE.findall(rest or "")}


def encode(values):
    """0..1 amplitudes -> one character each, stored as sqrt(amplitude) in 64 levels.

    The page draws the square-rooted value directly, which keeps quiet passages
    visible while preserving the loudness ordering between clips.
    """
    return "".join(LEVELS[min(63, round(math.sqrt(v) * 63))] for v in values)


def analyse_wav(path):
    """Return (duration, peak envelope, RMS envelope); envelopes are None if unreadable."""
    try:
        with wave.open(str(path), "rb") as w:
            channels, width, frames = w.getnchannels(), w.getsampwidth(), w.getnframes()
            duration = frames / w.getframerate()
            if width not in SAMPLE_TYPES or frames < BUCKETS * STRIDE:
                return duration, None, None
            typecode, full_scale = SAMPLE_TYPES[width]
            samples = array.array(typecode, w.readframes(frames))
    except (wave.Error, EOFError, OSError, ValueError):
        return None, None, None
    if sys.byteorder == "big":
        samples.byteswap()

    peaks, rms = [], []
    for b in range(BUCKETS):
        lo = frames * b // BUCKETS * channels
        hi = frames * (b + 1) // BUCKETS * channels
        peak = energy = count = 0
        for c in range(channels):
            seg = samples[lo + c : hi : channels * STRIDE]
            peak = max(peak, max(seg), -min(seg))
            energy += sumprod(seg, seg)
            count += len(seg)
        peaks.append(min(1.0, peak / full_scale))
        rms.append(math.sqrt(energy / count) / full_scale)
    return duration, encode(peaks), encode(rms)


def group_id(clip):
    """Value of the first key in the file name (10 for neg_0_prompt_10_variant_9): its line in the prompt list."""
    return next(iter(clip["meta"].values()), None)


def read_prompts(exp_dir):
    """Lines of the experiment's prompt list: prompts.txt, or else the folder's only .txt file."""
    named = exp_dir / "prompts.txt"
    candidates = [p for p in exp_dir.glob("*.txt") if not p.name.startswith(".")]
    if named.is_file():
        path = named
    elif len(candidates) == 1:
        path = candidates[0]
    else:
        if candidates:
            print(f"  {exp_dir.name}: several .txt files; name the prompt list prompts.txt to use it", file=sys.stderr)
        return None
    # Keep blank lines so line numbers still match prompt ids.
    return [line.strip() for line in path.read_text(errors="replace").splitlines()]


def build_experiment(exp_dir, site_root):
    directions = []
    for d in exp_dir.iterdir():
        match = DIRECTION_RE.fullmatch(d.name)
        if not (match and d.is_dir()):
            continue
        direction = {
            "id": int(match.group(1)),
            "path": Path(os.path.relpath(d, site_root)).as_posix(),
            "neg": [],
            "pos": [],
        }
        for f in sorted(d.iterdir()):
            if f.suffix.lower() not in AUDIO_EXTS:
                continue
            parsed = parse_clip(f)
            if not parsed:
                print(f"  skipping {f}: name should start with neg_<rank> or pos_<rank>", file=sys.stderr)
                continue
            side, rank, meta = parsed
            clip = {"file": f.name, "rank": rank, "meta": meta}
            if f.suffix.lower() == ".wav":
                duration, peak, rms = analyse_wav(f)
                if duration:
                    clip["dur"] = round(duration, 3)
                if peak:
                    clip["peak"], clip["rms"] = peak, rms
            direction[side].append(clip)
        for side in ("neg", "pos"):
            direction[side].sort(key=lambda clip: clip["rank"])
        directions.append(direction)
    directions.sort(key=lambda d: d["id"])

    experiment = {"name": exp_dir.name, "directions": directions}
    prompts = read_prompts(exp_dir)
    if prompts is not None:
        experiment["prompts"] = prompts
        clips = [clip for d in directions for side in ("neg", "pos") for clip in d[side]]
        unmatched = sum(1 for clip in clips if not (isinstance(group_id(clip), int) and 0 <= group_id(clip) < len(prompts)))
        if unmatched:
            print(f"  {exp_dir.name}: {unmatched} clips have no line in the {len(prompts)}-line prompt list", file=sys.stderr)
    config = exp_dir / ".hydra" / "config.yaml"
    if config.is_file():
        experiment["config"] = config.read_text(errors="replace")
    return experiment


def index_assets(assets, site_root):
    """Manifest for every experiment under `assets`, with paths relative to `site_root`."""
    if not assets.is_dir():
        sys.exit(f"No assets folder at {assets}")
    experiments = []
    for exp_dir in sorted(p for p in assets.resolve().iterdir() if p.is_dir() and not p.name.startswith(".")):
        start = time.perf_counter()
        experiment = build_experiment(exp_dir, site_root)
        if not experiment["directions"]:
            continue
        experiments.append(experiment)
        clips = sum(len(d["neg"]) + len(d["pos"]) for d in experiment["directions"])
        prompts = f", {len(experiment['prompts'])} prompts" if "prompts" in experiment else ""
        print(f"{exp_dir.name}: {len(experiment['directions'])} directions, {clips} clips{prompts} ({time.perf_counter() - start:.1f}s)")
    return {"experiments": experiments}


def write_manifest(manifest, out, script):
    payload = json.dumps(manifest, separators=(",", ":"))
    out.write_text(
        f"// Generated by {script}. Re-run it instead of editing this file.\n"
        f"window.FADERSPACE_MANIFEST = {payload};\n"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--assets", type=Path, default=HERE / "assets", help="folder of experiments (default: ./assets)")
    parser.add_argument("--out", type=Path, default=HERE / "manifest.js", help="output file (default: ./manifest.js)")
    args = parser.parse_args()

    manifest = index_assets(args.assets, args.out.resolve().parent)
    write_manifest(manifest, args.out, "build_manifest.py")
    print(f"Wrote {args.out.name} ({args.out.stat().st_size / 1024:.0f} KB, {len(manifest['experiments'])} experiments)")


if __name__ == "__main__":
    main()
