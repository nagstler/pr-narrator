"""pr-narrator: turn Claude Code sessions into reviewer-ready PR descriptions."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__: str = version("pr-narrator")
except PackageNotFoundError:  # pragma: no cover - only hit in unbuilt source trees
    __version__ = "0.0.0"

__all__ = ["__version__"]
