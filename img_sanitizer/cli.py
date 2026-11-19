"""Command-line interface for img-sanitizer.

Provides a small `typer`-based CLI exposing a `sanitize` command
which invokes the library's `Sanitizer` implementation.
"""

import logging
import time
from pathlib import Path
from typing import Annotated

import humanfriendly
import typer

import img_sanitizer
from img_sanitizer.sanitizer import Sanitizer

app = typer.Typer(help="Prepare, sanitize, and normalize JPEG images.")

EXIT_ERROR = 1
EXIT_INTERRUPTED = 130  # convention shell : 128 + SIGINT


@app.callback()
def common(
    ctx: typer.Context,
    debug: Annotated[
        bool,
        typer.Option("--debug", help="Enable debug logging", is_eager=True),
    ] = False,
) -> None:
    """Typer callback executed before subcommands.

    Configures logging level according to the `--debug` option.
    """
    ctx.ensure_object(dict)
    ctx.obj["debug"] = debug

    level = logging.DEBUG if debug else logging.INFO
    img_sanitizer.logger.setLevel(level)

    if debug:
        img_sanitizer.logger.debug("Debug mode enabled")


def _parse_sample_size(raw: str | None) -> int | None:
    """Convert a human-readable size (e.g. '512KiB', '2MB') to bytes."""
    if not raw:
        return None
    try:
        size = humanfriendly.parse_size(raw, binary=True)
    except humanfriendly.InvalidSize as e:
        raise typer.BadParameter(str(e), param_hint="--hash-sample-size") from e
    if size <= 0:
        raise typer.BadParameter("must be greater than 0", param_hint="--hash-sample-size")
    return size


def _check_dest_outside_source(source: Path, dest: Path) -> None:
    """Refuse a destination equal to, or nested inside, the source.

    Otherwise the next run would rescan already sanitized files.
    """
    if dest.resolve().is_relative_to(source.resolve()):
        raise typer.BadParameter(
            "destination must not be the source folder or located inside it",
            param_hint="DEST",
        )


@app.command()
def sanitize(
    ctx: typer.Context,
    source: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            dir_okay=True,
            readable=True,
            help="Source directory containing images",
        ),
    ],
    dest: Annotated[
        Path,
        typer.Argument(
            file_okay=False,
            dir_okay=True,
            help="Destination directory for sanitized images",
        ),
    ],
    worker: Annotated[
        int,
        typer.Option("--worker", min=1, help="Number of worker threads"),
    ] = 4,
    hash_sample_size_raw: Annotated[
        str | None,
        typer.Option(
            "--hash-sample-size",
            help=(
                "Partial hash: only the first N bytes are hashed "
                "(e.g., 512KiB, 2MB). Full file if not set."
            ),
        ),
    ] = None,
) -> None:
    """Command that sanitizes images in `source` and writes to `dest`.

    Files are renamed using a SHA-1 prefix, copied to `dest`, and
    their EXIF metadata is stripped (retaining orientation/ICC when
    present). Processing runs with multiple worker threads.
    """
    hash_sample_size = _parse_sample_size(hash_sample_size_raw)
    _check_dest_outside_source(source, dest)

    sanitizer = Sanitizer(source, dest, worker, hash_sample_size)
    exit_code = 0

    try:
        sanitizer.run()
    except KeyboardInterrupt:
        img_sanitizer.logger.warning("Process interrupted by user")
        exit_code = EXIT_INTERRUPTED
    except Exception as e:
        img_sanitizer.logger.error(
            "An error occurred: %s", e, exc_info=ctx.obj["debug"]
        )
        exit_code = EXIT_ERROR
    finally:
        img_sanitizer.logger.info(
            "Sanitization process ended after %.2f s.",
            time.monotonic() - sanitizer.start_time,
        )
        sanitizer.report.display()

    if exit_code == 0 and sanitizer.report.failed:
        exit_code = EXIT_ERROR

    if exit_code:
        raise typer.Exit(code=exit_code)


@app.command()
def version() -> None:
    """Display the current version of img-sanitizer."""
    typer.echo(img_sanitizer.__version__)


def main() -> None:
    """Entry point used by the console script; runs the Typer app."""
    app()