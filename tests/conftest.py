"""Shared fixtures for the img-sanitizer test suite."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import piexif
import pytest

# Smallest JPEG-like byte string that `piexif` can parse: SOI, a JFIF APP0
# segment, a start-of-scan marker, then EOI. It cannot be decoded as an
# image, which does not matter: img-sanitizer never decodes pixels.
_SOI = b"\xff\xd8"
_APP0 = b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
_SOS = b"\xff\xda\x00\x02"
_EOI = b"\xff\xd9"


@pytest.fixture
def src(tmp_path: Path) -> Path:
    path = tmp_path / "src"
    path.mkdir()
    return path


@pytest.fixture
def dst(tmp_path: Path) -> Path:
    path = tmp_path / "dst"
    path.mkdir()
    return path


@pytest.fixture
def make_jpeg() -> Callable[..., Path]:
    """Return a factory writing a minimal JPEG, optionally with EXIF.

    `payload` makes the content (and therefore the hash) unique.
    """

    def _make(
        path: Path, payload: bytes = b"", exif: dict[str, Any] | None = None
    ) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_SOI + _APP0 + _SOS + payload + _EOI)
        if exif is not None:
            piexif.insert(piexif.dump(exif), str(path))
        return path

    return _make


@pytest.fixture
def exif_with_gps() -> dict[str, Any]:
    """EXIF containing camera info, a date, GPS coordinates and an orientation."""
    return {
        "0th": {
            piexif.ImageIFD.Make: b"Canon",
            piexif.ImageIFD.Orientation: 6,
        },
        "Exif": {piexif.ExifIFD.DateTimeOriginal: b"2024:01:01 12:00:00"},
        "GPS": {
            piexif.GPSIFD.GPSLatitudeRef: b"N",
            piexif.GPSIFD.GPSLatitude: ((48, 1), (51, 1), (0, 1)),
            piexif.GPSIFD.GPSLongitudeRef: b"E",
            piexif.GPSIFD.GPSLongitude: ((2, 1), (21, 1), (0, 1)),
        },
    }
