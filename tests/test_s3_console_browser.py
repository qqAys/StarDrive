"""Opt-in real browser against a disposable app and loopback S3 protocol service."""

import hashlib
import json
import os
import signal
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.external
def test_s3_console_browser(tmp_path):
    tools_python = os.environ.get("STARDRIVE_BROWSER_TOOLS_PYTHON")
    if not tools_python:
        pytest.skip("Set STARDRIVE_BROWSER_TOOLS_PYTHON for the isolated browser suite")
    tree = Path(__file__).resolve().parents[1]
    output = Path(os.environ.get("STARDRIVE_BROWSER_OUTPUT", str(tmp_path / "browser")))
    output.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "STARDRIVE_BROWSER_OUTPUT": str(output),
        "STARDRIVE_BROWSER_APP_PYTHON": os.environ.get(
            "STARDRIVE_BROWSER_APP_PYTHON", sys.executable
        ),
    }
    # A child is a complete standalone application, not NiceGUI's pytest screen fixture.
    env.pop("PYTEST_CURRENT_TEST", None)
    with (output / "browser.log").open("w") as log:
        process = subprocess.Popen(
            [tools_python, str(tree / "tests/browser/s3_console_acceptance.py")],
            cwd=tree,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            code = process.wait(timeout=240)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise
    assert code == 0, f"Browser suite failed; inspect {output / 'browser.log'}"
    summary = json.loads((output / "summary.json").read_text())
    assert summary["completed"] == summary["attempted"] == 26
    assert summary["object_cleanup"] and summary["log_credentials_absent"]
    rows = json.loads((output / "browser-results.json").read_text())
    assert {row["viewport"] for row in rows} == {1280, 390}
    assert all(row["passed"] for row in rows)
    for path, digest in summary["application_source_sha256"].items():
        assert hashlib.sha256((tree / path).read_bytes()).hexdigest() == digest
