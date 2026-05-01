"""Tests for the package version export."""

import re

from pr_narrator import __version__


def test_version_is_non_empty_string() -> None:
    assert isinstance(__version__, str)
    assert __version__


def test_version_matches_semver_shape() -> None:
    assert re.match(r"^\d+\.\d+\.\d+", __version__)
