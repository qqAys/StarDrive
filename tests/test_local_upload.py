"""Fault-safe local uploads using only isolated synthetic files."""

import asyncio
import errno
import hashlib
import os
import stat
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.storage.base import StorageError, StoragePermissionError
from app.storage.local_storage import LocalStorage


async def chunks(*parts):
    for part in parts:
        yield part


def digest(path):
    return hashlib.sha256(path.read_bytes()).digest()


def assert_clean(root):
    assert list(root.rglob(".stardrive-upload-*.tmp")) == []


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("content", [b"", b"complete synthetic content" * 4096])
def test_upload_complete_and_permissions(tmp_path, existing, content):
    storage = LocalStorage(tmp_path)
    target = tmp_path / "nested" / "file.bin"
    target.parent.mkdir()
    if existing:
        target.write_bytes(b"old")
        target.chmod(0o640)
    # A normal file created with wb defines the existing umask policy.
    control = tmp_path / "control"
    control.write_bytes(b"")
    expected_mode = 0o640 if existing else stat.S_IMODE(control.stat().st_mode)
    asyncio.run(
        storage.upload_file(
            chunks(b"", content[:123], content[123:]), "nested/file.bin"
        )
    )
    assert target.read_bytes() == content
    assert stat.S_IMODE(target.stat().st_mode) == expected_mode
    assert_clean(tmp_path)


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize(
    "failure", ["iterator", "write", "close", "replace", "permission"]
)
def test_upload_failure_preserves_target(tmp_path, monkeypatch, existing, failure):
    storage = LocalStorage(tmp_path)
    target = tmp_path / "file.bin"
    if existing:
        target.write_bytes(b"original synthetic content")
    original_digest = digest(target) if existing else None
    real_fdopen = os.fdopen

    class FaultyFile:
        def __init__(self, fd, mode):
            self.file = real_fdopen(fd, mode)

        @property
        def closed(self):
            return self.file.closed

        def write(self, data):
            self.file.write(data[:2])
            if failure == "write":
                raise OSError(errno.ENOSPC, "synthetic full disk")
            if failure == "permission":
                raise PermissionError("synthetic permission failure")
            return self.file.write(data[2:])

        def close(self):
            self.file.close()
            if failure == "close":
                raise OSError("synthetic flush failure")

    if failure in ("write", "close", "permission"):
        monkeypatch.setattr(os, "fdopen", FaultyFile)
    if failure == "replace":

        def fail_replace(*args):
            raise OSError("synthetic replacement failure")

        monkeypatch.setattr(os, "replace", fail_replace)

    async def source():
        yield b"new partial data"
        # The original remains visible throughout reception.
        assert (digest(target) if existing else None) == original_digest
        if failure == "iterator":
            raise RuntimeError("synthetic interrupted source")
        yield b"complete"

    error = StoragePermissionError if failure == "permission" else StorageError
    with pytest.raises(error):
        asyncio.run(storage.upload_file(source(), "file.bin"))
    if existing:
        assert digest(target) == original_digest
    else:
        assert not target.exists()
    assert_clean(tmp_path)


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("cancel_at", ["receiving", "write", "failed_write"])
def test_cancel_waits_for_io_then_cleans(tmp_path, monkeypatch, existing, cancel_at):
    during_write = cancel_at != "receiving"
    storage = LocalStorage(tmp_path)
    target = tmp_path / "file.bin"
    if existing:
        target.write_bytes(b"old")
    started = threading.Event()
    release = threading.Event()
    closed = threading.Event()
    real_fdopen = os.fdopen

    class SlowFile:
        def __init__(self, fd, mode):
            self.file = real_fdopen(fd, mode)

        @property
        def closed(self):
            return self.file.closed

        def write(self, data):
            started.set()
            assert release.wait(5)
            assert not closed.is_set()
            if cancel_at == "failed_write":
                raise OSError(errno.ENOSPC, "synthetic full disk during cancellation")
            return self.file.write(data)

        def close(self):
            self.file.close()
            closed.set()

    if during_write:
        monkeypatch.setattr(os, "fdopen", SlowFile)

    async def run():
        receiving = asyncio.Event()

        async def source():
            yield b"partial"
            receiving.set()
            await asyncio.Event().wait()

        task = asyncio.create_task(storage.upload_file(source(), "file.bin"))
        try:
            if during_write:
                assert await asyncio.to_thread(started.wait, 5)
            else:
                await asyncio.wait_for(receiving.wait(), 5)
            task.cancel()
            await asyncio.sleep(0)
            if during_write:
                task.cancel()  # repeated cancellation must not abandon the worker
                await asyncio.sleep(0)
                assert not closed.is_set()
                assert not task.done()
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    assert target.read_bytes() == b"old" if existing else not target.exists()
    if during_write:
        assert closed.is_set()
    assert_clean(tmp_path)


def test_directory_target_is_preserved(tmp_path):
    storage = LocalStorage(tmp_path)
    target = tmp_path / "directory"
    target.mkdir()
    (target / "child").write_bytes(b"keep")
    with pytest.raises(StorageError):
        asyncio.run(storage.upload_file(chunks(b"new"), "directory"))
    assert (target / "child").read_bytes() == b"keep"
    assert_clean(tmp_path)


def test_concurrent_uploads_publish_complete_content(tmp_path):
    storage = LocalStorage(tmp_path)
    target = tmp_path / "file.bin"
    target.write_bytes(b"old")

    async def run():
        both_started = asyncio.Event()
        count = 0

        async def source(content):
            nonlocal count
            yield content[:20]
            assert target.read_bytes() == b"old"
            count += 1
            if count == 2:
                both_started.set()
            await both_started.wait()
            yield content[20:]

        first, second = b"A" * 20000, b"B" * 30000
        await asyncio.wait_for(
            asyncio.gather(
                storage.upload_file(source(first), "file.bin"),
                storage.upload_file(source(second), "file.bin"),
            ),
            5,
        )
        assert target.read_bytes() in (first, second)

    asyncio.run(run())
    assert_clean(tmp_path)


@pytest.mark.parametrize("fail", [False, True])
def test_browser_callback_storage_manager_roundtrip(tmp_path, monkeypatch, fail):
    from app.services.file_service import StorageManager
    from app.ui.components import table as table_module

    manager = StorageManager(root_path=tmp_path)
    manager.register_backend("local", LocalStorage(tmp_path))
    manager.set_current_backend("local")
    target = tmp_path / "file.bin"
    target.write_bytes(b"old")
    original_digest = digest(target)
    content = b"synthetic browser upload" * 2000

    async def source():
        yield content[:40]
        if fail:
            raise OSError("synthetic interrupted upload")
        yield content[40:]

    table = table_module.FileBrowserTable.__new__(table_module.FileBrowserTable)
    table.current_user = SimpleNamespace(is_active=True)
    monkeypatch.setattr(
        "app.security.guards.app",
        SimpleNamespace(storage=SimpleNamespace(user={"user_id": "synthetic-user"})),
    )
    monkeypatch.setattr(
        "app.security.guards.globals.get_user_manager",
        lambda: SimpleNamespace(
            current_user=AsyncMock(return_value=table.current_user)
        ),
    )
    table._current_path = Path("/")
    table.file_manager = manager
    table.upload_component = Mock()
    table.refresh = AsyncMock()
    monkeypatch.setattr(
        table_module, "can_user_store_bytes", AsyncMock(return_value=(True, 999999))
    )
    monkeypatch.setattr(
        table_module,
        "ConfirmDialog",
        Mock(return_value=SimpleNamespace(open=AsyncMock(return_value=True))),
    )
    notifications = Mock()
    monkeypatch.setattr(table_module, "notify", notifications)
    event = SimpleNamespace(
        files=[
            SimpleNamespace(name="file.bin", size=lambda: len(content), iterate=source)
        ]
    )
    asyncio.run(table.handle_upload(event))
    readback = b"".join(manager.download_file_with_stream("/file.bin"))
    assert hashlib.sha256(readback).digest() == (
        original_digest if fail else hashlib.sha256(content).digest()
    )
    assert table.refresh.await_count == (0 if fail else 1)
    assert notifications.error.call_count == int(fail)
    table.upload_component.reset.assert_called_once()
    assert_clean(tmp_path)


@pytest.mark.parametrize("operation", ["open", "chmod"])
def test_permission_failure_keeps_original(tmp_path, monkeypatch, operation):
    storage = LocalStorage(tmp_path)
    target = tmp_path / "file.bin"
    target.write_bytes(b"original")
    original_digest = digest(target)

    def denied(*args, **kwargs):
        raise PermissionError("synthetic permission failure")

    monkeypatch.setattr(os, operation, denied)
    with pytest.raises(StoragePermissionError):
        asyncio.run(storage.upload_file(chunks(b"replacement"), "file.bin"))
    assert digest(target) == original_digest
    assert_clean(tmp_path)


def test_cancel_during_close_does_not_publish(tmp_path, monkeypatch):
    storage = LocalStorage(tmp_path)
    target = tmp_path / "file.bin"
    target.write_bytes(b"old")
    closing = threading.Event()
    release = threading.Event()
    real_fdopen = os.fdopen

    class SlowClose:
        def __init__(self, fd, mode):
            self.file = real_fdopen(fd, mode)

        @property
        def closed(self):
            return self.file.closed

        def write(self, data):
            return self.file.write(data)

        def close(self):
            closing.set()
            assert release.wait(5)
            self.file.close()

    monkeypatch.setattr(os, "fdopen", SlowClose)

    async def run():
        task = asyncio.create_task(storage.upload_file(chunks(b"new"), "file.bin"))
        try:
            assert await asyncio.to_thread(closing.wait, 5)
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done()
            assert target.read_bytes() == b"old"
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    assert target.read_bytes() == b"old"
    assert_clean(tmp_path)


def test_browser_upload_rejects_missing_session(tmp_path, monkeypatch):
    from app.ui.components.table import FileBrowserTable

    target = tmp_path / "file.bin"
    target.write_bytes(b"old")
    table = FileBrowserTable.__new__(FileBrowserTable)
    table.file_manager = Mock()
    monkeypatch.setattr(
        "app.security.guards.app", SimpleNamespace(storage=SimpleNamespace(user={}))
    )
    monkeypatch.setattr("app.security.guards.notify", Mock())
    navigate = Mock()
    monkeypatch.setattr("app.security.guards.navigate_to", navigate)
    asyncio.run(table.handle_upload(SimpleNamespace(files=[])))
    table.file_manager.upload_file.assert_not_called()
    navigate.assert_called_once()
    assert target.read_bytes() == b"old"
    assert_clean(tmp_path)


def test_restrictive_permissions_apply_during_reception(tmp_path):
    storage = LocalStorage(tmp_path)
    target = tmp_path / "file.bin"
    target.write_bytes(b"old")
    target.chmod(0o600)

    async def source():
        yield b"partial"
        temporary = list(tmp_path.glob(".stardrive-upload-*.tmp"))
        assert len(temporary) == 1
        assert stat.S_IMODE(temporary[0].stat().st_mode) & 0o077 == 0
        assert target.read_bytes() == b"old"
        yield b"complete"

    asyncio.run(storage.upload_file(source(), "file.bin"))
    assert target.read_bytes() == b"partialcomplete"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert_clean(tmp_path)
