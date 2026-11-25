"""Real Chromium + application + loopback Moto S3; never accesses real services.

Install playwright and moto[server] into a separate tools environment; point
STARDRIVE_BROWSER_APP_PYTHON at the application environment and optionally set
STARDRIVE_BROWSER_CHROMIUM. Run this file from any directory. Artifacts go to
STARDRIVE_BROWSER_OUTPUT (default: a fresh system temporary directory).
"""

import hashlib
import json
import logging
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request

import boto3
from botocore.config import Config
from moto.server import DomainDispatcherApplication, create_backend_app
from playwright.sync_api import expect, sync_playwright, Locator, Page, Keyboard
from werkzeug.serving import make_server, WSGIRequestHandler

TREE = Path(__file__).resolve().parents[2]
OUT = Path(
    os.environ.get("STARDRIVE_BROWSER_OUTPUT") or tempfile.mkdtemp(prefix="s3-browser-")
)
OUT.mkdir(parents=True, exist_ok=True)
# Alembic's unchanged script_location is relative to cwd; keep deployment .env out.
(OUT / "migrations").symlink_to(TREE / "migrations", target_is_directory=True)
if (OUT / ".env").exists():
    raise RuntimeError("Use an output directory without an existing .env file")
PASSWORD = secrets.token_urlsafe(24)
KEY = secrets.token_hex(24)
SECRET = secrets.token_urlsafe(32)
CREDENTIALS = (secrets.token_hex(16), secrets.token_urlsafe(32))
results = []
operations = []


def measured(cls, name):
    original = getattr(cls, name)

    def call(self, *args, **kwargs):
        started = time.monotonic()
        try:
            return original(self, *args, **kwargs)
        finally:
            operations.append(
                {"action": name, "seconds": round(time.monotonic() - started, 4)}
            )

    setattr(cls, name, call)


for cls, methods in (
    (Locator, ("click", "fill", "press", "set_input_files")),
    (Page, ("goto",)),
    (Keyboard, ("press",)),
):
    for method in methods:
        measured(cls, method)

process = None
fault = {"mode": "", "delay": 0.0, "entered": False}


class QuietHandler(WSGIRequestHandler):
    def log(self, *args, **kwargs):
        pass


def middleware(environ, start_response):
    probe = "/.stardrive-probes/" in environ.get("PATH_INFO", "")
    method = environ["REQUEST_METHOD"]
    if probe and method == "PUT" and fault["delay"]:
        fault["entered"] = True
        time.sleep(fault["delay"])
    if probe and (
        fault["mode"] == "deny" or (fault["mode"] == "cleanup" and method == "DELETE")
    ):
        body = b"<Error><Code>AccessDenied</Code><Message>Synthetic denied</Message></Error>"
        start_response(
            "403 Forbidden",
            [("Content-Type", "application/xml"), ("Content-Length", str(len(body)))],
        )
        return [body]
    return moto_app(environ, start_response)


moto_app = DomainDispatcherApplication(create_backend_app)
s3 = make_server(
    "127.0.0.1", 0, middleware, threaded=True, request_handler=QuietHandler
)
threading.Thread(target=s3.serve_forever, daemon=True).start()
ENDPOINT = f"http://127.0.0.1:{s3.server_port}"
client = boto3.client(
    "s3",
    endpoint_url=ENDPOINT,
    region_name="us-east-1",
    aws_access_key_id=CREDENTIALS[0],
    aws_secret_access_key=CREDENTIALS[1],
    config=Config(s3={"addressing_style": "path"}),
)
client.create_bucket(Bucket="synthetic-browser")


def wait(predicate, message, timeout=30):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError(message)


def api(path="state", payload=None):
    request = urllib.request.Request(
        ORIGIN + "/api/fixture/" + path,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={"x-fixture-key": KEY, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


def ready():
    try:
        return api()["ready"]
    except OSError:
        return False


def start():
    global process
    process = subprocess.Popen(
        [
            os.environ.get(
                "STARDRIVE_BROWSER_APP_PYTHON", str(TREE / ".venv/bin/python")
            ),
            str(TREE / "tests/browser/s3_console_app.py"),
        ],
        # Config reads .env relative to cwd. Never load deployment settings.
        cwd=OUT,
        env=env,
        stdout=server_log,
        stderr=subprocess.STDOUT,
    )
    wait(ready, "Application did not start")


def stop():
    if process and process.poll() is None:
        process.terminate()
        process.wait(timeout=20)


def record(width, scenario, action):
    started = time.monotonic()
    before = len(operations)
    try:
        action()
    except BaseException:
        page.screenshot(path=str(OUT / "failure.png"), full_page=True)
        text = page.locator("body").inner_text()
        for value in (PASSWORD, SECRET, *CREDENTIALS):
            text = text.replace(value, "[redacted]")
        (OUT / "failure.txt").write_text(text)
        (OUT / "failed-scenario.json").write_text(
            json.dumps({"scenario": scenario, "viewport": width, "passed": False})
        )
        raise
    row = {
        "viewport": width,
        "scenario": scenario,
        "passed": True,
        "user_actions": len(operations) - before,
        "operations": operations[before:],
        "seconds": round(time.monotonic() - started, 3),
    }
    results.append(row)
    (OUT / "browser-results.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(row), flush=True)


def login(context, who="admin"):
    page = context.new_page()
    page.goto(ORIGIN + "/login/")
    page.get_by_label("Email", exact=True).fill(f"browser-{who}@example.com")
    page.locator("input[type=password]").fill(PASSWORD)
    page.get_by_role("button", name="Sign in", exact=True).click()
    page.wait_for_url("**/home/**")
    expect(page.locator(".q-table")).to_be_visible()
    return page


def console(page):
    page.goto(ORIGIN + "/console/")
    page.get_by_role("button", name="Storage backend", exact=True).click()
    expect(page.get_by_role("button", name="New profile", exact=True)).to_be_visible()
    if not page.evaluate("document.documentElement.scrollWidth <= innerWidth"):
        page.screenshot(path=str(OUT / "layout-failure.png"), full_page=True)
        (OUT / "layout-failure.json").write_text(
            json.dumps(
                page.evaluate(
                    """Array.from(document.querySelectorAll('body *')).filter(e=>e.getBoundingClientRect().right>innerWidth).map(e=>({tag:e.tagName,classes:e.className,width:e.getBoundingClientRect().width,left:e.getBoundingClientRect().left})).slice(0,25)"""
                ),
                indent=2,
            )
        )
        raise AssertionError("Console overflows viewport")
    table = page.locator(".q-table__container:visible")
    assert table.bounding_box()["width"] >= min(WIDTH - 40, 350)


def info(page, name):
    row = page.locator(".q-table tbody tr").filter(has_text=name)
    expect(row).to_have_count(1)
    row.click()
    expect(page.get_by_text("Storage profile information", exact=True)).to_be_visible()


def notify(page, text):
    expect(page.locator(".q-notification").filter(has_text=text).last).to_be_visible(
        timeout=15000
    )


def activate(page, name):
    info(page, name)
    page.get_by_role("button", name="Activate", exact=True).click()
    page.get_by_role("button", name="Confirm", exact=True).click()
    notify(page, "Storage profile activated.")
    expect(
        page.get_by_text("Storage profile information", exact=True)
    ).not_to_be_visible()


def test_saved(page, name, message):
    info(page, name)
    page.get_by_role("button", name="Test", exact=True).click()
    notify(page, message)
    expect(
        page.get_by_text("Storage profile information", exact=True)
    ).not_to_be_visible()


def new_profile(page, name):
    page.get_by_role("button", name="New profile", exact=True).click()
    page.get_by_label("Profile name", exact=True).fill(name)
    page.get_by_label("Profile name", exact=True).press("Tab")
    expect(page.get_by_label("Backend type", exact=True)).to_be_focused()
    page.get_by_label("Backend type", exact=True).click()
    page.get_by_role("option", name="S3 compatible", exact=True).click()
    for label, value in {
        "Region": "us-east-1",
        "Endpoint": ENDPOINT,
        "Bucket": "synthetic-browser",
        "AccessKey ID": CREDENTIALS[0],
        "AccessKey Secret": CREDENTIALS[1],
        "Object prefix": f"width-{WIDTH}",
    }.items():
        page.get_by_label(label, exact=True).fill(value)


def save(page):
    page.get_by_role("button", name="Save profile", exact=True).focus()
    page.keyboard.press("Enter")
    notify(page, "Storage profile saved.")
    expect(page.get_by_label("Profile name", exact=True)).not_to_be_visible()


def home(page):
    page.goto(ORIGIN + "/home/")
    expect(page.locator(".q-table")).to_be_visible()


def icon(page, name):
    return page.locator("button").filter(has=page.locator("i").filter(has_text=name))


def download(page, name, content):
    row = page.locator(".q-table tbody tr").filter(has_text=name)
    # The information dialog exposes the ordinary single-file download entry.
    row.locator("button").filter(has=page.locator("i").filter(has_text="info")).click()
    page.get_by_role("button", name="Download", exact=True).click()
    with page.expect_download() as event:
        page.get_by_role("button", name="Confirm", exact=True).click()
    downloaded = event.value
    assert (
        hashlib.sha256(Path(downloaded.path()).read_bytes()).digest()
        == hashlib.sha256(content).digest()
    )
    page.keyboard.press("Escape")


def upload_preview_download(page, name, content):
    home(page)
    icon(page, "cloud_upload").click()
    page.locator('input[type="file"]').set_input_files(
        {"name": name, "mimeType": "text/plain", "buffer": content}
    )
    expect(page.locator(".q-table")).to_contain_text(name, timeout=20000)
    page.locator(".q-dialog button").filter(
        has=page.locator("i").filter(has_text="close")
    ).click()
    row = page.locator(".q-table tbody tr").filter(has_text=name)
    row.get_by_role("button", name="Preview file", exact=True).click()
    expect(page.locator(".q-dialog--modal")).to_contain_text(content.decode())
    page.keyboard.press("Escape")
    download(page, name, content)


try:
    with sync_playwright() as pw:
        launch = {"headless": True}
        if os.environ.get("STARDRIVE_BROWSER_CHROMIUM"):
            launch["executable_path"] = os.environ["STARDRIVE_BROWSER_CHROMIUM"]
        browser = pw.chromium.launch(**launch)
        for WIDTH in map(
            int, os.environ.get("STARDRIVE_BROWSER_WIDTHS", "1280,390").split(",")
        ):
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            ORIGIN = f"http://127.0.0.1:{port}"
            data = OUT / f"data-{WIDTH}"
            if data.exists():
                raise RuntimeError(
                    "Use a fresh output directory; existing test data is preserved"
                )
            env = {
                # Preserve tool/runtime settings, but never inherit application
                # DB, SMTP, session storage or other deployment configuration.
                **{
                    key: value
                    for key, value in os.environ.items()
                    if not key.startswith(("STARDRIVE_", "STARDIVE_", "NICEGUI_"))
                    and key != "APP_SECRET"
                },
                "PYTHONPATH": str(TREE),
                "STARDIVE_APP_DATA_DIR": str(data),
                "STARDRIVE_APP_DATA_DIR": str(data),
                "STARDRIVE_APP_SECRET": SECRET,
                "FIXTURE_PASSWORD": PASSWORD,
                "FIXTURE_KEY": KEY,
                "FIXTURE_PORT": str(port),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            server_log = (OUT / f"application-{WIDTH}.log").open("w")
            contexts = [
                browser.new_context(
                    viewport={"width": WIDTH, "height": 900}, accept_downloads=True
                )
                for _ in range(2)
            ]
            start()
            page = login(contexts[0])
            other = login(contexts[1], "other")
            record(
                WIDTH,
                "original-local-download",
                lambda: download(page, "original.txt", b"original-admin"),
            )
            console(page)
            name = f"Synthetic S3 {WIDTH}"

            def configure():
                new_profile(page, name)
                page.get_by_label("Endpoint", exact=True).fill(ENDPOINT + "/invalid")
                page.get_by_role("button", name="Test draft", exact=True).click()
                notify(page, "Invalid S3 endpoint")
                page.get_by_label("Endpoint", exact=True).fill(ENDPOINT)
                page.get_by_role("button", name="Test draft", exact=True).click()
                notify(page, "Storage profile connection verified")
                save(page)
                test_saved(page, name, "Storage profile connection verified")
                activate(page, name)
                assert api()["active"] == "S3"

            record(WIDTH, "configure-test-activate", configure)

            def restart():
                stop()
                start()
                home(page)
                assert api()["active"] == "S3"
                expect(page.locator(".q-table")).not_to_contain_text("original.txt")

            record(WIDTH, "restart-active-profile", restart)
            payload = f"S3 browser bytes {WIDTH} 中文".encode()
            record(
                WIDTH,
                "upload-preview-download",
                lambda: upload_preview_download(page, "sample.txt", payload),
            )

            def isolated():
                home(other)
                expect(other.locator(".q-table")).not_to_contain_text("sample.txt")
                upload_preview_download(other, "other.txt", b"other user bytes")
                home(page)
                expect(page.locator(".q-table")).not_to_contain_text("other.txt")
                download(page, "sample.txt", payload)

            record(WIDTH, "dual-user-isolation", isolated)
            console(page)
            record(WIDTH, "switch-back-local", lambda: activate(page, "Local storage"))
            home(page)
            record(
                WIDTH,
                "original-local-restored",
                lambda: download(page, "original.txt", b"original-admin"),
            )
            console(page)

            def failed_recovery():
                fault["mode"] = "deny"
                test_saved(page, name, "S3 probe")
                info(page, name)
                page.get_by_role("button", name="Activate", exact=True).click()
                page.get_by_role("button", name="Confirm", exact=True).click()
                notify(page, "Test the saved S3 profile successfully before activation")
                assert api()["active"] != "S3"
                fault["mode"] = "cleanup"
                test_saved(page, name, "S3 probe cleanup failed")
                fault["mode"] = ""
                test_saved(page, name, "Storage profile connection verified")
                activate(page, name)

            record(WIDTH, "permission-cleanup-failure-recovery", failed_recovery)
            # A second real administrator page races a probe with an edit.
            activate(page, "Local storage")
            admin_context = browser.new_context(
                viewport={"width": WIDTH, "height": 900}
            )
            editor = login(admin_context)
            console(editor)

            def concurrent_edit():
                info(editor, name)
                editor.get_by_role("button", name="Edit", exact=True).click()
                editor.get_by_label("Object prefix", exact=True).fill(
                    f"width-{WIDTH}/edited"
                )
                fault.update(delay=2.0, entered=False)
                info(page, name)
                page.get_by_role("button", name="Test", exact=True).click()
                wait(lambda: fault["entered"], "Probe did not reach synthetic service")
                save(editor)
                wait(
                    lambda: next(p for p in api()["profiles"] if p["name"] == name)[
                        "tested"
                    ]
                    is None,
                    "Editing retained stale successful test",
                )
                expect(
                    page.get_by_text("Storage profile information", exact=True)
                ).not_to_be_visible()
                info(page, name)
                page.get_by_role("button", name="Activate", exact=True).click()
                page.get_by_role("button", name="Confirm", exact=True).click()
                notify(page, "Test the saved S3 profile successfully before activation")
                assert api()["active"] != "S3"
                fault["delay"] = 0
                test_saved(page, name, "Storage profile connection verified")

            record(WIDTH, "concurrent-test-edit-invalidates-result", concurrent_edit)

            def disconnect():
                fault.update(delay=2.0, entered=False)
                info(page, name)
                page.get_by_role("button", name="Test", exact=True).click()
                wait(lambda: fault["entered"], "Probe did not reach synthetic service")
                contexts[0].set_offline(True)
                time.sleep(2.5)
                contexts[0].set_offline(False)
                fault["delay"] = 0
                console(page)
                assert (
                    next(p for p in api()["profiles"] if p["name"] == name)["tested"]
                    is True
                )
                probes = client.list_objects_v2(
                    Bucket="synthetic-browser",
                    Prefix=f"width-{WIDTH}/edited/.stardrive-probes/",
                )
                assert not probes.get("Contents")
                activate(page, name)

            record(WIDTH, "disconnect-probe-cleanup-and-recover", disconnect)

            def revoked_admin():
                count = len(api()["profiles"])
                page.get_by_role("button", name="New profile", exact=True).click()
                api("user", {"admin": False})
                page.get_by_role("button", name="Save profile", exact=True).click()
                notify(page, "access to this page")
                assert len(api()["profiles"]) == count
                api("user", {"admin": True})
                console(page)
                info(page, name)
                page.get_by_role("button", name="Activate", exact=True).click()
                # Already-active response is also guarded; disabled callbacks must not run.
                page.keyboard.press("Escape")

            record(WIDTH, "stale-admin-callback-rejected", revoked_admin)

            def ordinary_user():
                other.goto(ORIGIN + "/console/")
                other.wait_for_url("**/home/**")
                expect(
                    other.get_by_role("button", name="New profile", exact=True)
                ).not_to_be_visible()

            record(WIDTH, "ordinary-user-console-rejected", ordinary_user)

            def disabled_user():
                count = len(api()["profiles"])
                console(page)
                page.get_by_role("button", name="New profile", exact=True).click()
                api("user", {"active": False})
                page.get_by_role("button", name="Save profile", exact=True).click()
                page.wait_for_url("**/login/**")
                assert len(api()["profiles"]) == count
                api("user", {"active": True})

            record(WIDTH, "disabled-admin-callback-rejected", disabled_user)
            page.close()
            page = login(contexts[0])
            admin_context.close()
            console(page)
            assert all(value not in page.content() for value in CREDENTIALS)
            page.screenshot(path=str(OUT / f"console-{WIDTH}.png"), full_page=True)
            for context in contexts:
                context.close()
            stop()
            server_log.close()
        browser.close()
    # Probe residue from the deliberately failed cleanup is explicit and is cleaned here.
    objects = client.list_objects_v2(Bucket="synthetic-browser").get("Contents", [])
    for obj in objects:
        client.delete_object(Bucket="synthetic-browser", Key=obj["Key"])
    assert not client.list_objects_v2(Bucket="synthetic-browser").get("Contents")
    hashes = {
        str(p.relative_to(TREE)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (TREE / "app").rglob("*.py")
    }
    (OUT / "source-hashes.json").write_text(json.dumps(hashes, indent=2))
    for logfile in OUT.glob("application-*.log"):
        text = logfile.read_text()
        assert all(value not in text for value in (PASSWORD, SECRET, *CREDENTIALS))
    for database in OUT.glob("data-*/db/local.db"):
        assert all(value.encode() not in database.read_bytes() for value in CREDENTIALS)
    (OUT / "summary.json").write_text(
        json.dumps(
            {
                "completed": len(results),
                "attempted": len(results),
                "application_source_sha256": hashes,
                "object_cleanup": True,
                "log_credentials_absent": True,
                "service": "loopback Moto, not real S3",
                "tool_versions": {"moto": __import__("moto").__version__},
            },
            indent=2,
        )
    )
except BaseException:
    if "page" in globals() and not page.is_closed():
        try:
            page.screenshot(path=str(OUT / "failure.png"), full_page=True)
            text = page.locator("body").inner_text()
            for value in (PASSWORD, SECRET, *CREDENTIALS):
                text = text.replace(value, "[redacted]")
            (OUT / "failure.txt").write_text(text)
        except Exception:
            pass
    raise
finally:
    stop()
    s3.shutdown()
