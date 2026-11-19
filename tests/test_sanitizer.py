"""Tests for img_sanitizer.sanitizer."""

import hashlib
import shutil
from pathlib import Path

import piexif
import pytest

from img_sanitizer.sanitizer import Sanitizer, Status


def short_sha(path: Path) -> str:
    """Short hash of a file's current content (as the sanitizer names it)."""
    return hashlib.sha1(path.read_bytes()).hexdigest()[:12]


def make_sanitizer(src: Path, dst: Path, worker: int = 1) -> Sanitizer:
    return Sanitizer(src, dst, worker=worker, hash_sample_size=None)


# --- hashing ---------------------------------------------------------------


def test_sha1_file(src, dst):
    f = src / "a.jpg"
    f.write_bytes(b"hello world")

    got = make_sanitizer(src, dst)._sha1_file(f)

    assert got == "2aae6c35c94fcfb415dbe95f408b9ce91ee846ed"


def test_sha1_sample_hashes_small_files_fully(src, dst):
    f = src / "a.jpg"
    f.write_bytes(b"12345678")  # 8 bytes <= 2 * sample size

    got = make_sanitizer(src, dst)._sha1_file(f, sample_size=4)

    assert got == hashlib.sha1(b"12345678").hexdigest()


def test_sha1_sample_covers_head_tail_and_size(src, dst):
    s = make_sanitizer(src, dst)

    def digest(name: str, data: bytes) -> str:
        f = src / name
        f.write_bytes(data)
        return s._sha1_file(f, sample_size=4)

    base = digest("base.jpg", b"AAAA" + b"x" * 10 + b"ZZZZ")

    # The middle of a large file is not hashed: known trade-off of sampling.
    assert digest("middle.jpg", b"AAAA" + b"y" * 10 + b"ZZZZ") == base
    assert digest("head.jpg", b"AAAB" + b"x" * 10 + b"ZZZZ") != base
    assert digest("tail.jpg", b"AAAA" + b"x" * 10 + b"ZZZY") != base
    assert digest("size.jpg", b"AAAA" + b"x" * 11 + b"ZZZZ") != base


# --- EXIF cleaning ---------------------------------------------------------


def test_clean_exif_keeps_only_orientation(src, dst, make_jpeg, exif_with_gps):
    img = make_jpeg(src / "img.jpg", exif=exif_with_gps)
    assert piexif.load(str(img))["GPS"]  # sanity check on the fixture

    make_sanitizer(src, dst)._clean_exif(img)

    after = piexif.load(str(img))
    assert after["0th"] == {piexif.ImageIFD.Orientation: 6}
    assert after["Exif"] == {}
    assert after["GPS"] == {}


def test_clean_exif_removes_everything_without_orientation(
    src, dst, make_jpeg, exif_with_gps
):
    exif = {"0th": {piexif.ImageIFD.Make: b"Canon"}, "GPS": exif_with_gps["GPS"]}
    img = make_jpeg(src / "img.jpg", exif=exif)

    make_sanitizer(src, dst)._clean_exif(img)

    after = piexif.load(str(img))
    assert after["0th"] == {}
    assert after["GPS"] == {}


def test_clean_exif_raises_on_invalid_jpeg(src, dst):
    img = src / "img.jpg"
    img.write_bytes(b"dummy")

    with pytest.raises(piexif.InvalidImageDataError):
        make_sanitizer(src, dst)._clean_exif(img)


# --- single file processing --------------------------------------------------


def test_process_file_copies_and_names(src, dst, make_jpeg):
    img = make_jpeg(src / "subdir" / "image.jpg", payload=b"hello")

    status = make_sanitizer(src, dst)._process_file(img)

    expected = dst / "subdir" / f"{short_sha(img)}.jpg"
    assert status is Status.COPIED
    assert list((dst / "subdir").iterdir()) == [expected]  # no leftover .part file


def test_process_file_strips_gps_and_keeps_orientation(
    src, dst, make_jpeg, exif_with_gps
):
    img = make_jpeg(src / "photo.jpg", exif=exif_with_gps)

    status = make_sanitizer(src, dst)._process_file(img)

    exif = piexif.load(str(dst / f"{short_sha(img)}.jpg"))
    assert status is Status.COPIED
    assert exif["GPS"] == {}
    assert exif["0th"] == {piexif.ImageIFD.Orientation: 6}
    assert piexif.load(str(img))["GPS"]  # the source file is left untouched


def test_process_file_ignores_known_hash(src, dst, make_jpeg):
    img = make_jpeg(src / "image.jpg")
    s = make_sanitizer(src, dst)
    s._known_hashes.add(short_sha(img))

    assert s._process_file(img) is Status.IGNORED
    assert list(dst.rglob("*")) == []


def test_process_file_ignores_identical_second_file(src, dst, make_jpeg):
    first = make_jpeg(src / "a" / "one.jpg", payload=b"same")
    second = make_jpeg(src / "b" / "two.jpg", payload=b"same")
    s = make_sanitizer(src, dst)

    assert s._process_file(first) is Status.COPIED
    assert s._process_file(second) is Status.IGNORED


def test_process_file_never_publishes_unsanitized_file(src, dst):
    bad = src / "bad.jpg"
    bad.write_bytes(b"not a jpeg")
    s = make_sanitizer(src, dst)

    assert s._process_file(bad) is Status.FAILED
    assert [p for p in dst.rglob("*") if p.is_file()] == []
    assert s._known_hashes == set()  # the hash is released after a failure


def test_process_file_copy_error_fails_and_releases_hash(
    src, dst, make_jpeg, monkeypatch
):
    img = make_jpeg(src / "img.jpg")

    def boom(*args, **kwargs):
        raise OSError("fail")

    monkeypatch.setattr(shutil, "copyfile", boom)
    s = make_sanitizer(src, dst)

    assert s._process_file(img) is Status.FAILED
    assert s._known_hashes == set()


def test_record_updates_report(src, dst):
    s = make_sanitizer(src, dst)

    for status in (Status.COPIED, Status.COPIED, Status.IGNORED, Status.FAILED):
        s._record(status)

    assert (s.report.copied, s.report.ignored, s.report.failed) == (2, 1, 1)


# --- whole run ---------------------------------------------------------------


def test_run_skips_existing(src, dst, make_jpeg):
    f1 = make_jpeg(src / "a" / "one.jpg", payload=b"aaa")
    f2 = make_jpeg(src / "b" / "two.jpg", payload=b"bbb")

    existing = dst / "a" / f"{short_sha(f1)}.jpg"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"exists")

    s = make_sanitizer(src, dst)
    s.run()

    assert (s.report.copied, s.report.ignored, s.report.failed) == (1, 1, 0)
    assert existing.read_bytes() == b"exists"
    assert (dst / "b" / f"{short_sha(f2)}.jpg").exists()


def test_run_copies_identical_files_only_once(src, dst, make_jpeg):
    for name in "abcde":
        make_jpeg(src / name / "img.jpg", payload=b"same")

    s = make_sanitizer(src, dst, worker=4)
    s.run()

    assert (s.report.copied, s.report.ignored, s.report.failed) == (1, 4, 0)
    assert len(list(dst.rglob("*.jpg"))) == 1


def test_scan_existing_hashes_only_matches_hashed_jpeg_names(src, dst):
    names = [
        "abcdef012345.jpg",  # match
        "3_ABCDEF012346.jpeg",  # match (numeric prefix, case-insensitive)
        "20240101123456.jpg",  # 14 digits: not a hash
        "abcdef012347.txt",  # not a JPEG
        "holiday.jpg",
    ]
    for name in names:
        (dst / name).write_bytes(b"x")

    got = make_sanitizer(src, dst)._scan_existing_hashes()

    assert got == {"abcdef012345", "abcdef012346"}