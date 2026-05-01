"""Tests for the pr-narrator CLI entry point."""

from click.testing import CliRunner

from pr_narrator import __version__
from pr_narrator.cli import main


def test_cli_prints_version_and_exits_zero() -> None:
    runner = CliRunner()
    result = runner.invoke(main)
    assert result.exit_code == 0
    assert result.output.strip() == f"pr-narrator v{__version__}"
