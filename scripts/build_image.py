#!/usr/bin/env python3
"""Build the StarDrive image using the version in pyproject.toml."""

from __future__ import annotations

import argparse
import shlex
import subprocess
import tomllib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IMAGE = "qqays/stardrive"


def project_version() -> str:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as file:
        return tomllib.load(file)["project"]["version"]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build StarDrive with CalVer and a latest convenience tag."
    )
    parser.add_argument("--image", default=DEFAULT_IMAGE, help="Image repository")
    parser.add_argument("--push", action="store_true", help="Push tags after building")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print commands without running Docker"
    )
    args = parser.parse_args()

    version = project_version()
    tags = [f"{args.image}:{version}", f"{args.image}:latest"]
    build_command = [
        "docker",
        "build",
        "--build-arg",
        f"APP_VERSION={version}",
        *[part for tag in tags for part in ("--tag", tag)],
        str(PROJECT_ROOT),
    ]
    commands = [build_command]
    if args.push:
        commands.extend([["docker", "push", tag] for tag in tags])

    for command in commands:
        print(shlex.join(command))
        if not args.dry_run:
            subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
