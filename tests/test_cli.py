"""Tests for img_sanitizer.cli."""

import pytest
import typer
from typer.testing import CliRunner

from img_sanitizer import cli

runner = CliRunner()


def test_cli_sanitize_runs(src, dst, make_jpeg):
    make_jpeg(src / "img.jpg", payload=b"cli")

    result = runner.invoke(cli.app, ["sanitize", str(src), str(dst)])

    assert result.exit_code == 0, result.output
    assert len(list(dst.rglob("*.jpg"))) == 1


def test_cli_accepts_hash_sample_size(src, dst, make_jpeg):
    make_jpeg(src / "img.jpg", payload=b"cli")

    result = runner.invoke(
        cli.app, ["sanitize", str(src), str(dst), "--hash-sample-size", "1KiB"]
    )

    assert result.exit_code == 0, result.output


def test_cli_exits_with_1_when_a_file_fails(src, dst):
    (src / "bad.jpg").write_bytes(b"not a jpeg")

    result = runner.invoke(cli.app, ["sanitize", str(src), str(dst)])

    assert result.exit_code == 1


def test_cli_rejects_destination_inside_source(src):
    result = runner.invoke(cli.app, ["sanitize", str(src), str(src / "out")])

    assert result.exit_code == 2


@pytest.mark.parametrize("value", ["nope", "0"])
def test_cli_rejects_invalid_hash_sample_size(src, dst, value):
    result = runner.invoke(
        cli.app, ["sanitize", str(src), str(dst), "--hash-sample-size", value]
    )

    assert result.exit_code == 2


def test_parse_sample_size():
    assert cli._parse_sample_size(None) is None
    assert cli._parse_sample_size("1KiB") == 1024
    with pytest.raises(typer.BadParameter):
        cli._parse_sample_size("nope")
