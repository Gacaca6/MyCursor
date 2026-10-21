# MyCursor beta launch package

The campaign uses Goldie's real `compose()` layout function in a native-canvas adapter for existing web-app captures. Motionmaxxing's unmodified runtime, renderer and quality scripts produce the film. No native mobile-app store listing is implied.

- `graphics/`: 12 final PNGs (1080×1350 feed, 1080×1920 story, square and widescreen hero).
- `film/final.mp4`: the 90-second 1080p master after rendering.
- `film/index.html`: editable, deterministic Motionmaxxing source.
- `film/audio/`: original code-composed electronic music.
- `BRIEF.md`, `STORYBOARD.md`, `LAUNCH-COPY.md`, `NOTE.md`: creative intent, copy, provenance and QA.

The film is designed for sound-off comprehension; no voiceover is used. Real product screenshots provide the UI. The document, projected slide, file receipt and offline connection drawings are illustrative demonstrations of documented capabilities. No real screen recording or benchmark result is claimed.

## Reproduce
From the repository root, install Node 22+, Python 3 with numpy, ffmpeg and Chrome. Download Goldie at `699578cefe908141433489125599d12a29a9f8db` into `tools/goldie` and Motionmaxxing at `8c8ec0f2a6f6c9a0da15cd24f7b1298ab298368c` into `tools/motionmaxxing`. Install launch/package.json dependencies in `launch/`.

```
node --experimental-strip-types launch/graphics.mjs
python launch/score.py
ffmpeg -y -i launch/film/audio/score.wav -af loudnorm=I=-14:TP=-1.5:LRA=7 -c:a aac -b:a 192k launch/film/audio/score.m4a
node launch/qa.mjs
node tools/motionmaxxing/scripts/lint.mjs launch/film/index.html
node tools/motionmaxxing/scripts/render.mjs launch/film/index.html launch/film/final.mp4 --audio launch/film/audio/score.m4a --crf 20 --preset fast
python tools/motionmaxxing/scripts/look.py launch/film/final.mp4 --out launch/look-final --expect 90 --expect-audio --strict
```

Set CHROME_PATH to the browser executable when automatic discovery cannot find it. Open index.html using a local HTTP server for a review; use Motionmaxxing's renderer for deterministic playback. The root timeline registers as `main` with a 90-second duration.

Graphics and video are release-ready beta creative. Publish when the beta is available. The owner confirmed all features are free during beta; no permanent pricing promise or launch date is inferred.
