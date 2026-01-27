"""Reporting utilities.

The `Report` object tracks counts of copied, ignored and failed
files and renders a small summary table to a `rich` console.
"""

from rich.align import Align
from rich.console import Console
from rich.table import Table


class Report:
    """Small container for processing counters and display.

    Attributes
    - ignored: number of files skipped because a matching digest exists
    - copied: number of files successfully copied
    - failed: number of files that failed processing
    """

    def __init__(self) -> None:
        self.ignored: int = 0
        self.copied: int = 0
        self.failed: int = 0
        self._console = Console()

    def display(self) -> None:
        """Render a short summary table to the configured console."""
        table = Table(show_edge=False, show_lines=False, expand=False)
        table.add_column("Status", style="bold cyan")
        table.add_column("Count", justify="right", style="bold green")

        table.add_row("Copied files", f"[green]{self.copied}[/green]")
        table.add_row("Ignored files", f"[yellow]{self.ignored}[/yellow]")
        table.add_row("Failed files", f"[red]{self.failed}[/red]")

        self._console.print(Align.center(table))
