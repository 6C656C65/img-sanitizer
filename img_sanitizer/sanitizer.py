"""Sanitizer implementation.

This module exposes the `Sanitizer` class which scans a source
directory for JPEG images, renames them using a SHA-1 digest,
copies them to a destination directory preserving relative
structure, and strips most EXIF metadata while keeping useful
fields such as orientation and ICC profile.
"""

import hashlib
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import piexif
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    track,
)

import img_sanitizer
from img_sanitizer.models import Image, Report


class Sanitizer:
    """Scan and sanitize JPEG images.

    Parameters
    - source: directory containing images to sanitize
    - dest: target directory where sanitized images will be written
    - worker: number of threads used when processing files
    """

    def __init__(
        self, source: Path, dest: Path, worker: int, hash_sample_size: int | None
    ) -> None:
        """Initialize a new `Sanitizer` instance.

        The constructor records a start time and prepares a `Report`
        instance as well as a `rich` progress renderer used during
        the `run` phase.
        """
        self.source = source
        self.dest = dest
        self.worker = worker
        self.start_time = time.monotonic()

        self.report = Report()

        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=img_sanitizer.console,
        )

        self._hash_sample_size: int | None = hash_sample_size

    def run(self) -> None:
        """Execute the sanitization pipeline.

        This scans the source directory for JPEG files, skips any
        files that appear to already exist in the destination (by
        comparing computed SHA-1 prefixes), and processes files in
        parallel using a thread pool.
        """
        img_sanitizer.logger.debug("Hash sample size set to %s", self._hash_sample_size)
        img_sanitizer.logger.info("Scanning source folder for images...")
        files: list[Path] = [
            f for f in self.source.rglob("*") if f.suffix.lower() in {".jpg", ".jpeg"}
        ]
        img_sanitizer.logger.info("Found %s image(s) in source folder.", len(files))

        img_sanitizer.logger.info("Scanning destination folder for existing files...")
        hash_pattern = re.compile(r"(?:^\d+_)?([a-f0-9]{12})", re.IGNORECASE)

        existing_hashes: set[str] = set()

        for f in self.dest.rglob("*"):
            if f.is_file():
                match = hash_pattern.search(f.stem)
                if match:
                    existing_hashes.add(match.group(1).lower())
        img_sanitizer.logger.info(
            "Found %s existing file(s) in destination.", len(existing_hashes)
        )

        with ThreadPoolExecutor(max_workers=self.worker) as executor:
            for _ in track(
                executor.map(lambda f: self._process_file(f, existing_hashes), files),
                total=len(files),
                description="[bold blue]Processing images...",
                console=self._progress.console,
            ):
                pass

    def _process_file(self, src_path: Path, existing_hashes: set[str]) -> None:
        """Process a single file: copy and sanitize EXIF.

        The method computes a short SHA-1 digest used as the new
        filename, copies the file to the destination (preserving the
        relative path) and attempts to clean EXIF metadata. Errors
        are caught and reflected in the `Report`.
        """
        try:
            sha1 = self._sha1_file(src_path, sample_size=self._hash_sample_size)
            image = Image(path=src_path, sha1=sha1)

            if image.short_sha in existing_hashes:
                img_sanitizer.logger.debug("Ignored (SHA1 exists): %s", image.path)
                self.report.ignored += 1
                return

            dst_path = self._copy_image(image)
            self._clean_exif(dst_path)

            img_sanitizer.logger.info("Processed: %s", dst_path)
            self.report.copied += 1

        except Exception as e:
            img_sanitizer.logger.error("Error on %s : %s", src_path, e)
            self.report.failed += 1

    def _sha1_file(
        self, filepath: Path, buffer_size: int = 65536, sample_size: int | None = None
    ) -> str:
        """Compute and return the SHA-1 digest of a file as hex.

        The digest is computed by reading the file in chunks to avoid
        large memory usage for big images. The full hex digest is
        returned (the caller may truncate it for shorter file names).

        If `sample_size` provided, only the first `sample_size` bytes
        of the file are hashed. Useful for fast deduplication of large files.
        If None, the full file is hashed.
        """
        h = hashlib.sha1()
        remaining = sample_size

        with filepath.open("rb") as f:
            while True:
                chunk_size = (
                    buffer_size if remaining is None else min(buffer_size, remaining)
                )
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                h.update(chunk)
                if remaining is not None:
                    remaining -= len(chunk)
                    if remaining <= 0:
                        break

        sha1 = h.hexdigest()
        img_sanitizer.logger.debug("SHA1 of %s : %s", filepath, sha1)
        return sha1

    def _clean_exif(self, path: Path) -> None:
        """Remove most EXIF tags while keeping orientation and ICC.

        Loads EXIF via `piexif`, builds a minimal EXIF dict containing
        only orientation and ICC profile (when present) and writes the
        stripped metadata back into the file. Errors are caught and
        reported.
        """
        try:
            exif_dict = piexif.load(str(path))

            orientation = exif_dict["0th"].get(piexif.ImageIFD.Orientation)
            icc_profile = exif_dict.get("ICC")

            new_exif: dict[str, Any] = {
                "0th": {},
                "Exif": {},
                "GPS": {},
                "1st": {},
                "Interop": {},
                "thumbnail": None,
            }

            if orientation:
                new_exif["0th"][piexif.ImageIFD.Orientation] = orientation
            if icc_profile:
                new_exif["ICC"] = icc_profile

            exif_bytes = piexif.dump(new_exif)
            piexif.insert(exif_bytes, str(path))

        except Exception as e:
            img_sanitizer.logger.error("Error on %s : %s", path, e)
            self.report.failed += 1
            return

    def _copy_image(self, image: Image) -> Path:
        """Copy an image to the destination with a new name.

        The new name is built using the first 12 characters of the
        SHA-1 digest, preserving the original file extension. The
        relative path from source to the image is preserved in the
        destination directory. Necessary directories are created as
        needed.
        """
        relative_dir = image.path.parent.relative_to(self.source)
        final_dir = self.dest / relative_dir
        final_dir.mkdir(parents=True, exist_ok=True)

        new_name = f"{image.short_sha}{image.extension}"
        dst_path = final_dir / new_name

        shutil.copy2(image.path, dst_path)
        return dst_path
