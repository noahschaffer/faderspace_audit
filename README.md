# faderspace audition

A static page for listening to the strongest negative and positive examples along each PCA direction, side by side.

## Usage

1. Put each experiment under `assets/<experiment>/direction_<k>/`, with clips named
   `neg_<rank>_…wav` and `pos_<rank>_…wav` (rank 0 = strongest). Any `key_value` pairs after the
   rank, such as `prompt_10_variant_9`, are shown on the clip. A `.hydra/config.yaml` next to the
   directions is shown under "Run config".

   To show prompt text, add the prompt list to the experiment folder, one prompt per line:
   `assets/<experiment>/prompts.txt`, or any name if it's the folder's only `.txt` file. Line N
   (counting from 0) is shown on every clip named `prompt_N`.
2. Index the audio. Re-run this whenever you add or change experiments:

   ```bash
   python3 build_manifest.py
   ```

3. Serve the folder and open http://localhost:8000:

   ```bash
   python3 -m http.server 8000
   ```

   Opening `index.html` straight from disk works too.

The indexer only uses the Python standard library. It writes `manifest.js`, which lists every clip with a small
waveform envelope, so the page never has to list directories or decode audio to draw waveforms.

## Publishing on GitHub Pages

The published copy lives in `docs/`, which GitHub Pages serves from the `main` branch. The WAVs are too
heavy to publish, so it is built with MP3s:

```bash
python3 build_site.py
```

This rewrites `docs/`: the same page, its manifest, and one MP3 per direction
(`audio/<experiment>/direction_<k>.mp3`, each direction's clips at 192 kbps stored back to back; the page
cuts each clip out by byte range). `musiccaps_trumpet` comes to about 150 MB, and GitHub Pages takes sites
up to 1 GB. To check it locally, open http://localhost:8000/docs/ with the server from step 3.

`assets/` and the local `manifest.js` are not committed (see `.gitignore`), so the repository holds the
code and `docs/`.

One-time setup:

1. On GitHub, create a public repository named `faderspace_audit`, with "Add a README" left unchecked.
   This folder's `origin` already points at it.
2. Push:

   ```bash
   git push -u origin main
   ```

3. In the repository, open Settings → Pages, choose "Deploy from a branch", then branch `main` and
   folder `/docs`, and save.

The page appears at https://noahschaffer.github.io/faderspace_audit/ a minute or two later. Links to a
direction look like `https://noahschaffer.github.io/faderspace_audit/#musiccaps_trumpet.17`.

To update it, re-run `python3 build_site.py`, then commit and push. The site is public: anyone with the
link can listen, and the "Run config" panel shows the cluster path from `.hydra/config.yaml`.

## Keyboard

| Key | Action |
| --- | --- |
| `Space` | Play / pause the selected example |
| `↑` `↓` | Previous / next example (playback follows if something is playing) |
| `←` `→` | Negative / positive side, same rank |
| `1`–`9` | Play that rank on the current side |
| `[` `]` | Previous / next direction |
| `A` | Toggle auto-advance (play the next example when one ends) |
| `Esc` | Stop |

Click a waveform to play from that point. Hover a clip's prompt number to highlight the other examples from the same prompt.
Cards show the first two lines of each prompt; the bar at the bottom shows the selected example's full prompt.
The URL tracks the experiment and direction (`#musiccaps_trumpet.17`), so links reopen the same view.
