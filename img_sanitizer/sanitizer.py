"""Sanitizer implementation.

This module exposes the `Sanitizer` class which scans a source
directory for JPEG images, renames them using a SHA-1 digest,
copies them to a destination directory preserving relative
structure, and strips most EXIF metadata while keeping the
orientation tag and the ICC profile.
"""

import hashlib
import os
import re
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum, auto
from pathlib import Path
from typing import Any, BinaryIO

import piexif
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

import img_sanitizer
from img_sanitizer.models import Image, Report

JPEG_SUFFIXES = {".jpg", ".jpeg"}

# Names produced by this tool: "<12 hex chars>", optionally prefixed by "<n>_".
HASHED_NAME = re.compile(r"(?:\d+_)?([a-f0-9]{12})", re.IGNORECASE)


class Status(Enum):
    """Outcome of the processing of a single file."""

    COPIED = auto()
    IGNORED = auto()
    FAILED = auto()


def _feed(h: Any, f: BinaryIO, length: int, buffer_size: int) -> None:
    """Feed `length` bytes (or less, if EOF comes first) of `f` into hash `h`."""
    remaining = length
    while remaining > 0:
        chunk = f.read(min(buffer_size, remaining))
        if not chunk:
            break
        h.update(chunk)
        remaining -= len(chunk)


class Sanitizer:
    """Scan and sanitize JPEG images.

    Parameters
    - source: directory containing images to sanitize
    - dest: target directory where sanitized images will be written
    - worker: number of threads used when processing files
    - hash_sample_size: number of bytes hashed at each end of a file
      (None to hash the whole file)
    """

    def __init__(
        self, source: Path, dest: Path, worker: int, hash_sample_size: int | None
    ) -> None:
        """Initialize a new `Sanitizer` instance.

        The constructor records a start time and prepares a `Report`
        instance. Counters of the report are only updated from the
        calling thread, never from the workers.
        """
        self.source = source
        self.dest = dest
        self.worker = worker
        self.start_time = time.monotonic()

        self.report = Report()

        self._hash_sample_size: int | None = hash_sample_size
        self._known_hashes: set[str] = set()
        self._lock = threading.Lock()

    def run(self) -> None:
        """Execute the sanitization pipeline.

        This scans the source directory for JPEG files, skips any
        file whose hash is already known (present in the destination
        or already handled during this run), and processes the others
        in parallel using a thread pool.

        A `KeyboardInterrupt` cancels the queued files, waits for the
        files being processed, then is propagated to the caller.
        """
        img_sanitizer.logger.debug("Hash sample size set to %s", self._hash_sample_size)
        self.dest.mkdir(parents=True, exist_ok=True)

        img_sanitizer.logger.info("Scanning source folder for images...")
        files: list[Path] = [
            f
            for f in self.source.rglob("*")
            if f.is_file() and f.suffix.lower() in JPEG_SUFFIXES
        ]
        img_sanitizer.logger.info("Found %s image(s) in source folder.", len(files))

        img_sanitizer.logger.info("Scanning destination folder for existing files...")
        self._known_hashes = self._scan_existing_hashes()
        img_sanitizer.logger.info(
            "Found %s known hash(es) in destination.", len(self._known_hashes)
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=img_sanitizer.console,
        ) as progress:
            task = progress.add_task("Processing images...", total=len(files))

            executor = ThreadPoolExecutor(max_workers=self.worker)
            try:
                futures = [executor.submit(self._process_file, f) for f in files]
                for future in as_completed(futures):
                    self._record(future.result())
                    progress.advance(task)
            finally:
                # No-op once everything is done; on Ctrl+C or error, drops the
                # queued files and waits only for the ones already running.
                executor.shutdown(wait=True, cancel_futures=True)

    def _scan_existing_hashes(self) -> set[str]:
        """Collect the short hashes of the images already in the destination."""
        hashes: set[str] = set()
        for f in self.dest.rglob("*"):
            if f.is_file() and f.suffix.lower() in JPEG_SUFFIXES:
                match = HASHED_NAME.fullmatch(f.stem)
                if match:
                    hashes.add(match.group(1).lower())
        return hashes

    def _record(self, status: Status) -> None:
        """Update the report (called from the main thread only)."""
        match status:
            case Status.COPIED:
                self.report.copied += 1
            case Status.IGNORED:
                self.report.ignored += 1
            case Status.FAILED:
                self.report.failed += 1

    def _process_file(self, src_path: Path) -> Status:
        """Process a single file: copy, sanitize EXIF, then publish.

        The image is copied to a temporary file, stripped of its
        metadata, and only then moved to its final name. A file whose
        metadata cannot be stripped is therefore never left in the
        destination.
        """
        reserved_sha: str | None = None
        tmp_path: Path | None = None

        try:
            sha1 = self._sha1_file(src_path, sample_size=self._hash_sample_size)
            image = Image(path=src_path, sha1=sha1)

            # Check and reserve atomically so that two identical files
            # cannot be processed at the same time.
            with self._lock:
                if image.short_sha in self._known_hashes:
                    img_sanitizer.logger.debug("Ignored (SHA1 exists): %s", image.path)
                    return Status.IGNORED
                self._known_hashes.add(image.short_sha)
                reserved_sha = image.short_sha

            tmp_path, dst_path = self._copy_to_temp(image)
            self._clean_exif(tmp_path)
            os.replace(tmp_path, dst_path)

            img_sanitizer.logger.info("Processed: %s", dst_path)
            return Status.COPIED

        except Exception as e:
            img_sanitizer.logger.error("Error on %s : %s", src_path, e)
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)
            if reserved_sha is not None:
                with self._lock:
                    self._known_hashes.discard(reserved_sha)
            return Status.FAILED

    def _sha1_file(
        self, filepath: Path, buffer_size: int = 65536, sample_size: int | None = None
    ) -> str:
        """Compute and return the SHA-1 digest of a file as hex.

        The file is read in chunks to avoid large memory usage.

        If `sample_size` is None, or if the file is not larger than
        twice that size, the whole file is hashed. Otherwise the digest
        covers the file size, its first `sample_size` bytes and its last
        `sample_size` bytes: much faster on large files, and far less
        prone to false duplicates than hashing the head alone.
        """
        h = hashlib.sha1()

        with filepath.open("rb") as f:
            size = os.fstat(f.fileno()).st_size

            if sample_size is None or size <= 2 * sample_size:
                _feed(h, f, size, buffer_size)
            else:
                h.update(size.to_bytes(8, "big"))
                _feed(h, f, sample_size, buffer_size)
                f.seek(-sample_size, os.SEEK_END)
                _feed(h, f, sample_size, buffer_size)

        sha1 = h.hexdigest()
        img_sanitizer.logger.debug("SHA1 of %s : %s", filepath, sha1)
        return sha1

    def _clean_exif(self, path: Path) -> None:
        """Remove EXIF metadata from a JPEG, keeping only the orientation.

        The ICC profile lives in a separate APP2 segment which `piexif`
        never touches, so it is preserved without any special handling.

        Raises on failure: the caller must not publish a file whose
        metadata could not be stripped.
        """
        exif_dict = piexif.load(str(path))
        orientation = exif_dict["0th"].get(piexif.ImageIFD.Orientation)

        if orientation:
            new_exif: dict[str, Any] = {
                "0th": {piexif.ImageIFD.Orientation: orientation},
                "Exif": {},
                "GPS": {},
                "1st": {},
                "Interop": {},
                "thumbnail": None,
            }
            piexif.insert(piexif.dump(new_exif), str(path))
        else:
            piexif.remove(str(path))

    def _copy_to_temp(self, image: Image) -> tuple[Path, Path]:
        """Copy an image next to its final location, under a temporary name.

        The final name is built using the first 12 characters of the
        SHA-1 digest, preserving the original file extension. The
        relative path from source to the image is preserved in the
        destination directory, and missing directories are created.

        Returns `(tmp_path, final_path)`. The caller moves the temporary
        file to its final name once it has been sanitized.
        """
        relative_dir = image.path.parent.relative_to(self.source)
        final_dir = self.dest / relative_dir
        final_dir.mkdir(parents=True, exist_ok=True)

        final_path = final_dir / f"{image.short_sha}{image.extension}"
        tmp_path = final_dir / f".{image.short_sha}.part{image.extension}"

        shutil.copyfile(image.path, tmp_path)
        return tmp_path, final_path