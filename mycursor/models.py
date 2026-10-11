"""Model file management.

MediaPipe's task bundles are not shipped inside the pip package, so we fetch
them once on first run and cache them beside the code.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parent.parent / "models"

_BASE = "https://storage.googleapis.com/mediapipe-models"
SOURCES = {
    "hand_landmarker.task": f"{_BASE}/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
    "face_landmarker.task": f"{_BASE}/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
}

# A truncated download would fail later as an opaque model-parse error, so
# sanity-check the size instead.
_MIN_BYTES = 100_000


class ModelUnavailable(RuntimeError):
    pass


def ensure(name: str, quiet: bool = False) -> Path:
    """Return a local path to the named model, downloading it if needed."""
    if name not in SOURCES:
        raise KeyError(f"unknown model {name!r}")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    path = MODEL_DIR / name

    if path.exists() and path.stat().st_size >= _MIN_BYTES:
        return path

    url = SOURCES[name]
    if not quiet:
        print(f"  downloading {name} ...", flush=True)
    tmp = path.with_suffix(path.suffix + ".part")
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            tmp.write_bytes(response.read())
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        tmp.unlink(missing_ok=True)
        raise ModelUnavailable(
            f"Could not download {name} from {url}\n"
            f"  reason: {exc}\n"
            f"  Fix: download it manually and save it as {path}"
        ) from exc

    if tmp.stat().st_size < _MIN_BYTES:
        size = tmp.stat().st_size
        tmp.unlink(missing_ok=True)
        raise ModelUnavailable(
            f"{name} downloaded but is only {size} bytes, which cannot be a "
            f"valid model. Check your connection and retry."
        )

    tmp.replace(path)
    if not quiet:
        print(f"  saved {name} ({path.stat().st_size // 1024} KB)", flush=True)
    return path
