"""Welcome photo of the login: real people, shown in turn with the map.

The first image in ``assets/login`` (JPG, PNG or WebP) takes turns with the map of Ecuador; the institutional purple tints
it so both read as one design.  Without an image, the login shows the map alone.  No data is shown before authentication.
"""
from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

FOLDER = Path(__file__).resolve().parents[1] / "assets" / "login"
TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


@lru_cache(maxsize=4)
def _figure(path: str, version: int) -> str:
    source = Path(path)
    data = base64.b64encode(source.read_bytes()).decode("ascii")
    return (f'<figure class="login-photo"><img src="data:{TYPES[source.suffix.lower()]};base64,{data}" '
            'alt="Personas sonrientes" loading="eager" decoding="async"/></figure>')


def photo() -> str:
    """The figure with the welcome photo, or an empty text when ``assets/login`` has none."""
    files = sorted(p for p in FOLDER.glob("*") if p.suffix.lower() in TYPES) if FOLDER.exists() else []
    return _figure(str(files[0]), files[0].stat().st_mtime_ns) if files else ""
