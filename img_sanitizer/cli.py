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


@app.callback()
def common(
    ctx: typer.Context,
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Enable debug logging",
        is_eager=True,
    ),
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


@app.command()
def sanitize(
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
    worker: int = typer.Option(
        4,
        "--worker",
        min=1,
        help="Number of worker threads",
    ),
    hash_sample_size: str = typer.Option(
        None,
        "--hash-sample-size",
        help="Partial hash: only the first N bytes are hashed (e.g., 512K, 2MB, 1Mo). Full file if not set.",
    ),
) -> None:
    """Command that sanitizes images in `source` and writes to `dest`.

    Files are renamed using a SHA-1 prefix, copied to `dest`, and
    their EXIF metadata is stripped (retaining orientation/ICC when
    present). Processing runs with multiple worker threads.
    """
    if hash_sample_size:
        hash_sample_size = humanfriendly.parse_size(hash_sample_size)
    sanitizer = Sanitizer(source, dest, worker, hash_sample_size)

    try:
        sanitizer.run()
    except KeyboardInterrupt:
        img_sanitizer.logger.warning("Process interrupted by user")
    except Exception as e:
        img_sanitizer.logger.error("An error occurred: %s", e)

    finally:
        img_sanitizer.logger.info(
            "Sanitization process completed in %.2f s.",
            time.monotonic() - sanitizer.start_time,
        )
        sanitizer.report.display()


@app.command()
def version() -> None:
    """Display the current version of img-sanitizer."""
    typer.echo(img_sanitizer.__version__)


def main() -> None:
    """Entry point used by the console script; runs the Typer app."""
    app()
