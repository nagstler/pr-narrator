"""Command-line entry point for pr-narrator."""

from __future__ import annotations

import click

from pr_narrator import __version__


@click.command()
def main() -> None:
    """Print the pr-narrator version and exit."""
    click.echo(f"pr-narrator v{__version__}")
