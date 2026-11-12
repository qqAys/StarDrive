"""Private archive regression tests with isolated synthetic data."""

import asyncio
import io
import json
import threading
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel
from starlette.requests import Request
from fastapi import HTTPException
from app.storage.base import StorageFileNotFoundError

from app.api.download import download_form_browser_api
from app.models.file_download_model import FileDownloadInfo
from app.schemas.file_schema import FileSource, FileType
from app.services import file_service
from app.services.file_service import AsyncStreamWriter, StorageManager
from app.utils.time import utc_now


def record(**overrides):
    values = dict(
        name="bulk_download",
        path=json.dumps({"version": 1, "paths": ["a", "b", "folder"]}),
        type=FileType.MIXED,
        base_path=".",
        user_id="synthetic-owner",
        source=FileSource.DOWNLOAD,
        expires_at=utc_now() + timedelta(minutes=5),
    )
    values.update(overrides)
    return FileDownloadInfo(**values)


def test_batch_record_survives_sqlite_restart_and_legacy_paths(tmp_path):
    url = f"sqlite:///{tmp_path / 'downloads.db'}"
    engine = create_engine(url)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        batch = record()
        session.add(batch)
        session.commit()
        download_id = batch.id
    engine.dispose()
    engine = create_engine(url)
    with Session(engine) as session:
        assert session.get(FileDownloadInfo, download_id).archive_paths == [
            "a",
            "b",
            "folder",
        ]
    engine.dispose()
    for kind in [FileType.FILE, FileType.DIR]:
        assert record(type=kind, path='["literal"]').archive_paths == ['["literal"]']
    with pytest.raises(ValueError):
        record(path='{"version": 2, "paths": ["a"]}').archive_paths


def manager(root):
    storage = StorageManager(root_path=root)
    storage.set_current_backend(file_service.LocalStorage.name)
    return storage


def test_private_http_archive_contents_and_legacy_downloads(tmp_path, monkeypatch):
    import tarfile
    from app.api import download

    (tmp_path / "a").write_bytes(b"alpha")
    (tmp_path / "b").write_bytes(b"beta")
    (tmp_path / "folder").mkdir()
    (tmp_path / "folder" / "c").write_bytes(b"gamma")
    storage = manager(tmp_path)
    monkeypatch.setattr(download, "create_user_storage_manager", lambda owner: storage)
    monkeypatch.setattr(
        download,
        "globals",
        SimpleNamespace(
            get_user_manager=lambda: SimpleNamespace(
                current_user=AsyncMock(
                    return_value=SimpleNamespace(id="synthetic-owner")
                )
            )
        ),
    )
    request = Request({"type": "http", "headers": []})

    async def fetch(info):
        response = await download_form_browser_api(info, request)
        return b"".join([chunk async for chunk in response.body_iterator])

    data = asyncio.run(asyncio.wait_for(fetch(record()), 3))
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        assert archive.getnames() == ["a", "b", "folder", "folder/c"]
        for path, content in [("a", b"alpha"), ("b", b"beta"), ("folder/c", b"gamma")]:
            assert archive.extractfile(path).read() == content
    assert (
        asyncio.run(fetch(record(type=FileType.FILE, name="a", path="a"))) == b"alpha"
    )
    asyncio.run(fetch(record(type=FileType.DIR, name="folder", path="folder")))


@pytest.mark.parametrize("paths", [[], [1], ["../outside"], ["missing"]])
def test_archive_preflight_rejects_invalid_or_missing_sources(tmp_path, paths):
    async def collect():
        return [
            chunk
            async for chunk in manager(tmp_path).download_file_with_compressed_stream(
                paths, "."
            )
        ]

    with pytest.raises((ValueError, FileNotFoundError, StorageFileNotFoundError)):
        asyncio.run(asyncio.wait_for(collect(), 2))


def test_archive_read_failure_propagates_and_closes_stream(tmp_path, monkeypatch):
    (tmp_path / "a").write_bytes(b"alpha")
    storage = manager(tmp_path)
    closed = threading.Event()

    def fail(*args):
        try:
            yield b"a"
            raise OSError("Synthetic read failure")
        finally:
            closed.set()

    monkeypatch.setattr(storage, "download_file_with_stream", fail)

    async def collect():
        return [
            part
            async for part in storage.download_file_with_compressed_stream(["a"], ".")
        ]

    with pytest.raises(OSError, match="Synthetic read failure"):
        asyncio.run(asyncio.wait_for(collect(), 2))
    assert closed.is_set()


def test_channel_zero_output_error_and_bounded_disconnect():
    async def check():
        writer = AsyncStreamWriter()
        writer.close()
        assert [part async for part in writer] == []
        writer = AsyncStreamWriter()
        writer.error = OSError("Synthetic producer failure")
        with pytest.raises(OSError):
            await anext(writer.__aiter__())
        writer = AsyncStreamWriter()
        finished = threading.Event()

        def produce():
            try:
                writer.write(b"x" * 2**20)
            except InterruptedError:
                pass
            finally:
                finished.set()

        thread = threading.Thread(target=produce)
        thread.start()
        try:
            await asyncio.sleep(0.1)
            assert writer.queue.qsize() == writer.queue.maxsize
            assert not finished.is_set()
        finally:
            writer.stopped.set()
            await asyncio.to_thread(thread.join, 1)
        assert finished.is_set()

    asyncio.run(asyncio.wait_for(check(), 3))


@pytest.mark.parametrize(
    "paths,names", [([], []), (["a", 1], ["a", "b"]), (["a"], "a")]
)
def test_generate_rejects_invalid_selection(paths, names):
    with pytest.raises(ValueError):
        asyncio.run(
            file_service.generate_download_url(
                paths, names, FileType.MIXED, FileSource.DOWNLOAD
            )
        )


def test_expired_download_token_is_rejected(monkeypatch):
    from app.services import download_service

    monkeypatch.setattr(
        download_service, "decode_token", lambda token: {"download_id": "synthetic"}
    )
    monkeypatch.setattr(
        download_service,
        "get_download_info",
        AsyncMock(return_value=record(expires_at=utc_now() - timedelta(seconds=1))),
    )
    assert asyncio.run(download_service.verify_download_token("synthetic")) is None


def test_private_download_rejects_other_account(monkeypatch):
    from app.api import download

    monkeypatch.setattr(
        download,
        "globals",
        SimpleNamespace(
            get_user_manager=lambda: SimpleNamespace(
                current_user=AsyncMock(
                    return_value=SimpleNamespace(id="other-synthetic-owner")
                )
            )
        ),
    )
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            download_form_browser_api(
                record(), Request({"type": "http", "headers": []})
            )
        )
    assert error.value.status_code == 403


def test_archive_disconnect_releases_producer_and_source(tmp_path, monkeypatch):
    (tmp_path / "a").write_bytes(b"a")
    storage = manager(tmp_path)
    closed = threading.Event()
    channel_closed = threading.Event()
    original_close = AsyncStreamWriter.close

    def close(writer):
        original_close(writer)
        channel_closed.set()

    def chunks(*args):
        import os

        try:
            for _ in range(200):
                yield os.urandom(65536)
        finally:
            closed.set()

    metadata = storage.get_file_metadata("a")
    metadata.size = 200 * 65536
    monkeypatch.setattr(storage, "get_file_metadata", lambda path: metadata)
    monkeypatch.setattr(storage, "download_file_with_stream", chunks)
    monkeypatch.setattr(AsyncStreamWriter, "close", close)

    async def consume():
        stream = storage.download_file_with_compressed_stream(["a"], ".")
        await anext(stream)
        await stream.aclose()

    asyncio.run(asyncio.wait_for(consume(), 3))
    assert closed.is_set()
    assert channel_closed.is_set()


def test_source_disappears_after_preflight(tmp_path, monkeypatch):
    (tmp_path / "a").write_bytes(b"synthetic")
    storage = manager(tmp_path)
    monkeypatch.setattr(storage, "exists", lambda path: False)

    async def consume():
        return [
            part
            async for part in storage.download_file_with_compressed_stream(["a"], ".")
        ]

    with pytest.raises(FileNotFoundError):
        asyncio.run(asyncio.wait_for(consume(), 2))


def test_share_directory_archive_keeps_existing_entry_path(tmp_path, monkeypatch):
    from app.api import download

    (tmp_path / "folder").mkdir()
    storage = manager(tmp_path)
    monkeypatch.setattr(download, "create_user_storage_manager", lambda owner: storage)

    async def consume():
        response = await download_form_browser_api(
            record(
                type=FileType.DIR,
                path="folder",
                name="folder",
                share_id="synthetic-share",
            ),
            Request({"type": "http", "headers": []}),
        )
        return b"".join([part async for part in response.body_iterator])

    assert asyncio.run(asyncio.wait_for(consume(), 2))


def test_generate_persists_versioned_selection(monkeypatch):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def database():
        yield object()

    created = AsyncMock(return_value=record())
    monkeypatch.setattr(file_service, "get_db_context", database)
    monkeypatch.setattr(file_service.FileDownloadCRUD, "create", created)
    monkeypatch.setattr(file_service.FileDownloadCRUD, "update_url", AsyncMock())
    monkeypatch.setattr(
        file_service, "create_token", lambda *args, **kwargs: "synthetic"
    )
    monkeypatch.setattr(
        file_service,
        "app",
        SimpleNamespace(
            storage=SimpleNamespace(
                general={"service_url": "http://testserver"}, user={"last_path": "."}
            )
        ),
    )
    url = asyncio.run(
        file_service.generate_download_url(
            ["a", "b", "folder"],
            ["a", "b", "folder"],
            FileType.MIXED,
            FileSource.DOWNLOAD,
            current_user=SimpleNamespace(id="synthetic-owner"),
        )
    )
    values = created.call_args.kwargs
    assert values["type"] == FileType.MIXED
    assert values["name"] == "bulk_download"
    assert json.loads(values["path"]) == {
        "version": 1,
        "paths": ["a", "b", "folder"],
    }
    assert url.endswith("/api/download-form-browser/synthetic")


@pytest.mark.parametrize(
    "state", ["active", "anonymous", "revoked", "disabled", "other"]
)
def test_private_http_validates_current_session(tmp_path, monkeypatch, state):
    from contextlib import asynccontextmanager
    from fastapi import FastAPI
    import httpx
    from app.api import download
    from app.services import user_service
    from app.services.user_service import UserManager

    (tmp_path / "a").write_bytes(b"synthetic")
    user = SimpleNamespace(
        id="other" if state == "other" else "synthetic-owner",
        is_active=state != "disabled",
        must_change_password=False,
        token_version=2 if state == "revoked" else 1,
    )
    session_data = (
        {}
        if state == "anonymous"
        else {
            "email": "synthetic@example.test",
            "token_version": 1,
            "user_id": "synthetic-owner",
        }
    )

    @asynccontextmanager
    async def database():
        yield None

    user_manager = UserManager(
        user_crud=SimpleNamespace(get_by_email=AsyncMock(return_value=user)),
        db_context=database,
    )
    monkeypatch.setattr(
        user_service, "app", SimpleNamespace(storage=SimpleNamespace(user=session_data))
    )
    monkeypatch.setattr(download.globals, "get_user_manager", lambda: user_manager)
    monkeypatch.setattr(
        download,
        "create_user_storage_manager",
        lambda owner: manager(tmp_path),
    )
    application = FastAPI()
    application.include_router(download.router)
    application.dependency_overrides[download.verify_download_token] = lambda: record(
        type=FileType.FILE, name="a", path="a"
    )

    async def fetch():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application), base_url="http://synthetic"
        ) as client:
            response = await client.get("/api/download-form-browser/synthetic")
            assert response.status_code == (200 if state == "active" else 403)
            if state == "active":
                assert response.content == b"synthetic"

    asyncio.run(fetch())
    if state in {"revoked", "disabled"}:
        assert session_data == {}


@pytest.mark.parametrize("failure", ["disconnect", "send", "cancel"])
def test_archive_asgi_disconnect_and_send_failure(tmp_path, monkeypatch, failure):
    from app.api.download import DownloadStreamingResponse
    from starlette.requests import ClientDisconnect
    import os

    (tmp_path / "a").write_bytes(b"synthetic")
    storage = manager(tmp_path)
    closed = threading.Event()
    done = threading.Event()
    original_close = AsyncStreamWriter.close

    def close(writer):
        original_close(writer)
        done.set()

    def chunks(*args):
        try:
            for _ in range(200):
                yield os.urandom(65536)
        finally:
            closed.set()

    metadata = storage.get_file_metadata("a")
    metadata.size = 200 * 65536
    monkeypatch.setattr(storage, "get_file_metadata", lambda path: metadata)
    monkeypatch.setattr(storage, "download_file_with_stream", chunks)
    monkeypatch.setattr(AsyncStreamWriter, "close", close)

    async def run():
        sent = asyncio.Event()
        response = DownloadStreamingResponse(
            storage.download_file_with_compressed_stream(["a"], ".")
        )

        async def receive():
            await sent.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.body" and message.get("body"):
                sent.set()
                # Let the bounded queue fill while the transport is blocked.
                await asyncio.sleep(0.1)
                if failure == "send":
                    raise OSError("Synthetic transport failure")
                await asyncio.Event().wait()

        task = asyncio.create_task(
            response(
                {
                    "type": "http",
                    "asgi": {
                        "spec_version": "2.0" if failure == "disconnect" else "2.4"
                    },
                },
                receive,
                send,
            )
        )
        if failure == "cancel":
            await sent.wait()
            task.cancel()
        if failure == "disconnect":
            await task
        else:
            with pytest.raises(
                asyncio.CancelledError if failure == "cancel" else ClientDisconnect
            ):
                await task
        assert closed.is_set()
        assert done.is_set()

    asyncio.run(asyncio.wait_for(run(), 3))


def test_batch_record_backup_isolation_and_restore(tmp_path):
    import shutil
    from sqlmodel import select

    path = tmp_path / "downloads.db"
    engine = create_engine(f"sqlite:///{path}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(record())
        session.add(record(type=FileType.FILE, path="a", name="a"))
        session.commit()
    engine.dispose()
    backup = tmp_path / "backup.db"
    shutil.copyfile(path, backup)
    engine = create_engine(f"sqlite:///{path}")
    with Session(engine) as session:
        for row in session.exec(
            select(FileDownloadInfo).where(FileDownloadInfo.type == FileType.MIXED)
        ):
            session.delete(row)
        session.commit()
        remaining = session.exec(select(FileDownloadInfo)).all()
        assert len(remaining) == 1 and remaining[0].archive_paths == ["a"]
    engine.dispose()
    shutil.copyfile(backup, path)
    engine = create_engine(f"sqlite:///{path}")
    with Session(engine) as session:
        restored = session.exec(select(FileDownloadInfo)).all()
        assert sorted(row.archive_paths for row in restored) == [
            ["a"],
            ["a", "b", "folder"],
        ]
    engine.dispose()
