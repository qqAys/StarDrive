"""Application version resolution from the canonical package metadata."""

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import tomllib


PACKAGE_NAME = "stardrive"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def app_version() -> str:
    """Return installed package metadata, or pyproject metadata for source runs."""
    try:
        return version(PACKAGE_NAME)
    except PackageNotFoundError:
        with (PROJECT_ROOT / "pyproject.toml").open("rb") as file:
            return tomllib.load(file)["project"]["version"]
