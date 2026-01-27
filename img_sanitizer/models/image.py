"""Image model used by the sanitizer.

This module defines the lightweight `Image` dataclass which bundles
the original file `path` with its computed `sha1` digest. Utility
properties expose the original filename, normalized extension and a
12-character short SHA prefix used for destination file names.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Image:
    """Immutable container for image metadata used during processing.

    Attributes
    - path: `pathlib.Path` referencing the original image file
    - sha1: full SHA-1 hex digest of the file contents
    """

    path: Path
    sha1: str

    @property
    def filename(self) -> str:
        """Return the base filename of the image (no directory)."""
        return self.path.name

    @property
    def extension(self) -> str:
        """Return the file extension in lower case, including the dot."""
        return self.path.suffix.lower()

    @property
    def short_sha(self) -> str:
        """Return the first 12 characters of the SHA-1 digest."""
        return self.sha1[:12]
