"""Package entrypoint for img_sanitizer.

Exposes a preconfigured `rich` console and a module logger used by
the CLI and sanitizer implementation.
"""

import logging

from rich.console import Console
from rich.logging import RichHandler

console = Console()

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=console, rich_tracebacks=True)],
)

logger = logging.getLogger(__package__)

__version__ = "0.1.0"
