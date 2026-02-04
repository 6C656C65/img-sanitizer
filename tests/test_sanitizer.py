import hashlib
import shutil

from img_sanitizer import cli
from img_sanitizer.sanitizer import Sanitizer


def test_sha1_file(tmp_path):
    data = b"hello world"
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    f = src_dir / "a.jpg"
    f.write_bytes(data)

    s = Sanitizer(src_dir, tmp_path / "dst", worker=1, hash_sample_size=None)
    got = s._sha1_file(f)
    assert got == "2aae6c35c94fcfb415dbe95f408b9ce91ee846ed"


def test_process_file_copies_and_names(tmp_path):
    data = b"hello world"
    src_dir = tmp_path / "src"
    dest_dir = tmp_path / "dst"
    src_dir.mkdir()
    dest_dir.mkdir()

    f = src_dir / "subdir"
    f.mkdir()
    img = f / "image.jpg"
    img.write_bytes(data)

    s = Sanitizer(src_dir, dest_dir, worker=1, hash_sample_size=None)

    # process the file directly
    s._process_file(img, existing_hashes=set())

    sha1 = hashlib.sha1(data).hexdigest()[:12]
    expected_path = dest_dir / "subdir" / f"{sha1}.jpg"

    assert expected_path.exists(), f"Expected copied file at {expected_path}"
    assert s.report.copied == 1


def test_clean_exif_handles_piexif_error(tmp_path, monkeypatch):
    # simulate piexif.load raising an error and ensure report increments
    def fake_load(path):
        raise ValueError("bad exif")

    monkeypatch.setattr("img_sanitizer.sanitizer.piexif.load", fake_load)

    img = tmp_path / "img.jpg"
    img.write_bytes(b"dummy")

    s = Sanitizer(tmp_path, tmp_path / "dst", worker=1, hash_sample_size=None)
    s._clean_exif(img)

    assert s.report.failed == 1


def test_clean_exif_calls_insert_with_minimal_exif(tmp_path, monkeypatch):
    # verify piexif.insert is called with dumped bytes when load returns a dict
    recorded = {}

    def fake_load(path):
        return {"0th": {}}

    def fake_dump(exif_dict):
        return b"exifbytes"

    def fake_insert(exif_bytes, path):
        recorded["inserted"] = exif_bytes

    monkeypatch.setattr("img_sanitizer.sanitizer.piexif.load", fake_load)
    monkeypatch.setattr("img_sanitizer.sanitizer.piexif.dump", fake_dump)
    monkeypatch.setattr("img_sanitizer.sanitizer.piexif.insert", fake_insert)

    img = tmp_path / "img.jpg"
    img.write_bytes(b"dummy")

    s = Sanitizer(tmp_path, tmp_path / "dst", worker=1, hash_sample_size=None)
    s._clean_exif(img)

    assert recorded.get("inserted") == b"exifbytes"


def test_run_skips_existing(tmp_path):
    # create two images
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    (src / "a").mkdir(parents=True)
    (src / "b").mkdir(parents=True)

    f1 = src / "a" / "one.jpg"
    f2 = src / "b" / "two.jpg"
    f1.write_bytes(b"aaa")
    f2.write_bytes(b"bbb")

    # create existing file in dest with sha1 of f1
    sha1_f1 = hashlib.sha1(b"aaa").hexdigest()[:12]
    existing = dst / "a"
    existing.mkdir(parents=True)
    (existing / f"{sha1_f1}.jpg").write_bytes(b"exists")

    s = Sanitizer(src, dst, worker=1, hash_sample_size=None)
    s.run()

    # one should be ignored (f1), one copied (f2)
    assert s.report.ignored >= 1
    assert s.report.copied >= 1


def test_process_file_copy_error_increments_failed(tmp_path, monkeypatch):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()
    img = src / "bad.jpg"
    img.write_bytes(b"data")

    def boom(src, dst2):
        raise OSError("fail")

    monkeypatch.setattr(shutil, "copy2", boom)

    s = Sanitizer(src, dst, worker=1, hash_sample_size=None)
    s._process_file(img, existing_hashes=set())

    assert s.report.failed == 1


def test_cli_sanitize_runs(tmp_path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()
    (src / "img.jpg").write_bytes(b"\xff\xd8\xff\xd9")

    # call the CLI command directly
    cli.sanitize(src, dst, worker=1, hash_sample_size_raw=None)
