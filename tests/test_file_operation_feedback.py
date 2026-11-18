import asyncio
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from alibabacloud_oss_v2.exceptions import OperationError, ServiceError
from alibabacloud_oss_v2.models import (
    CommonPrefix,
    DeletedInfo,
    DeleteMultipleObjectsResult,
)

from app.security import guards
from app.services.file_service import StorageManager
from app.storage.aliyun_oss_storage import AliyunOSSStorage
from app.ui.components import dialog, table


@pytest.mark.parametrize("is_dir", [False, True])
@pytest.mark.parametrize("failed", [False, True])
def test_metadata_delete_dispatch_and_refresh(monkeypatch, is_dir, failed):
    confirmation = Mock()
    confirmation.open = AsyncMock(return_value=True)
    monkeypatch.setattr(dialog, "ConfirmDialog", Mock(return_value=confirmation))
    notifications = SimpleNamespace(success=Mock(), error=Mock(), warning=Mock())
    monkeypatch.setattr(dialog, "notify", notifications)
    manager = Mock()
    operation = manager.delete_directory if is_dir else manager.delete_file
    if failed:
        operation.side_effect = RuntimeError("synthetic failure")
    target = SimpleNamespace(
        metadata=SimpleNamespace(path="sample", name="sample"),
        is_dir=is_dir,
        file_manager=manager,
        refresh_browser=AsyncMock(),
    )
    asyncio.run(dialog.MetadataDialog.on_delete_button_click(target))
    operation.assert_called_once_with("sample")
    target.refresh_browser.assert_awaited_once()
    assert notifications.success.called == (not failed)
    assert notifications.warning.called == failed


class SyntheticOSS:
    """Keep object state at the SDK boundary so callbacks use the real driver."""

    def __init__(self):
        self.objects = {
            "source/report.txt": b"report",
            "source/sub/data.txt": b"data",
            "target/": b"",
            "first.txt": b"first",
            "last.txt": b"last",
        }
        self.copy_failure = None
        self.unconfirmed = set()

    def list_objects_v2(self, request):
        contents = []
        prefixes = set()
        for key, data in sorted(self.objects.items()):
            if not key.startswith(request.prefix):
                continue
            name, slash, _ = key.removeprefix(request.prefix).partition("/")
            if request.delimiter and slash:
                prefixes.add(request.prefix + name + "/")
            else:
                contents.append(
                    SimpleNamespace(key=key, size=len(data), last_modified=None)
                )
        return SimpleNamespace(
            contents=contents,
            common_prefixes=[CommonPrefix(prefix=key) for key in sorted(prefixes)],
            is_truncated=False,
        )

    def head_object(self, request):
        if request.key not in self.objects:
            raise ServiceError(
                status_code=404,
                code="NoSuchKey",
                request_id="synthetic",
                message="Object missing",
                ec="",
                timestamp="",
                request_target="synthetic",
            )
        return SimpleNamespace(
            content_length=len(self.objects[request.key]), last_modified=None
        )

    def get_object(self, request):
        data = self.objects[request.key]
        body = MagicMock()
        body.__enter__.return_value.iter_bytes.return_value = iter([data])
        return SimpleNamespace(body=body)

    def copy_object(self, request):
        if request.source_key == self.copy_failure:
            raise OperationError(
                name="CopyObject", error=TimeoutError("copy timed out")
            )
        self.objects[request.key] = self.objects[request.source_key]

    def delete_object(self, request):
        del self.objects[request.key]

    def delete_multiple_objects(self, request):
        confirmed = []
        for item in request.delete.objects:
            if item.key not in self.unconfirmed:
                del self.objects[item.key]
                confirmed.append(DeletedInfo(key=item.key))
        return DeleteMultipleObjectsResult(deleted_objects=confirmed)


@pytest.fixture
def oss_browser(monkeypatch, tmp_path):
    client = SyntheticOSS()
    backend = AliyunOSSStorage.__new__(AliyunOSSStorage)
    backend.config = SimpleNamespace(bucket="synthetic")
    backend.root_prefix = "users/synthetic"
    backend.client = client
    client.objects = {
        f"{backend.root_prefix}/{path}": data for path, data in client.objects.items()
    }
    manager = StorageManager(root_path=tmp_path)
    manager.register_backend(backend.name, backend)
    manager.set_current_backend(backend.name)

    notifications = Mock()
    monkeypatch.setattr(table, "notify", notifications)
    monkeypatch.setattr(dialog, "notify", notifications)
    monkeypatch.setattr(
        guards,
        "app",
        SimpleNamespace(storage=SimpleNamespace(user={"signed_in": True})),
    )
    monkeypatch.setattr(
        guards.globals,
        "get_user_manager",
        lambda: SimpleNamespace(
            current_user=AsyncMock(return_value=SimpleNamespace(is_active=True))
        ),
    )
    browser = table.FileBrowserTable.__new__(table.FileBrowserTable)
    browser._current_path = Path(".")
    browser._refresh_lock = asyncio.Lock()
    browser.file_manager = manager
    browser.browser_table = SimpleNamespace(rows=[], selected=[])

    def update_rows():
        browser.browser_table.rows = [
            {
                "path": entry.path,
                "raw_name": entry.name,
                "type": entry.type.value,
                "extension": entry.extension,
            }
            for entry in manager.list_files(str(browser.current_path))
        ]
        browser.browser_table.selected = []

    browser.refresh_func = SimpleNamespace(
        targets=[object()], refresh=AsyncMock(side_effect=update_rows)
    )
    update_rows()
    return client, manager, browser, notifications


def select_rows(browser, *paths):
    by_path = {row["path"]: row for row in browser.browser_table.rows}
    browser.browser_table.selected = [by_path[path] for path in paths]


def confirm_with(monkeypatch, module, dialog_name, value):
    monkeypatch.setattr(
        module,
        dialog_name,
        Mock(return_value=SimpleNamespace(open=AsyncMock(return_value=value))),
    )


def visible_paths(browser):
    return {row["path"] for row in browser.browser_table.rows}


def assert_partial_feedback(notifications):
    notifications.success.assert_not_called()
    notifications.error.assert_called_once()
    notifications.warning.assert_called_once()
    assert "before retrying" in notifications.warning.call_args.args[0]


def test_batch_delete_refreshes_partial_result_and_retries(oss_browser, monkeypatch):
    client, manager, browser, notifications = oss_browser
    confirm_with(monkeypatch, table, "ConfirmDialog", True)
    client.unconfirmed.add("users/synthetic/source/sub/data.txt")
    select_rows(browser, "first.txt", "source", "last.txt")

    asyncio.run(browser.handle_delete_button_click())

    assert_partial_feedback(notifications)
    browser.refresh_func.refresh.assert_awaited_once()
    assert visible_paths(browser) == {"source", "last.txt", "target"}
    assert manager.download_file("source/sub/data.txt") == b"data"
    assert not manager.exists("source/report.txt")

    client.unconfirmed.clear()
    notifications.reset_mock()
    select_rows(browser, "source", "last.txt")
    asyncio.run(browser.handle_delete_button_click())

    notifications.success.assert_called_once_with("Deleted 2 items")
    notifications.error.assert_not_called()
    notifications.warning.assert_not_called()
    assert visible_paths(browser) == {"target"}


@pytest.mark.parametrize("failure", ["copy", "delete"])
def test_batch_move_preserves_data_and_retries(oss_browser, monkeypatch, failure):
    client, manager, browser, notifications = oss_browser
    confirm_with(monkeypatch, table, "MoveDialog", Path("target"))
    if failure == "copy":
        client.copy_failure = "users/synthetic/source/sub/data.txt"
    else:
        client.unconfirmed.add("users/synthetic/source/sub/data.txt")
    select_rows(browser, "first.txt", "source")

    asyncio.run(browser.handle_move_button_click())

    assert_partial_feedback(notifications)
    browser.refresh_func.refresh.assert_awaited_once()
    assert visible_paths(browser) == {"source", "last.txt", "target"}
    assert manager.download_file("target/first.txt") == b"first"
    assert manager.download_file("source/sub/data.txt") == b"data"
    assert manager.exists("source/report.txt") == (failure == "copy")
    if failure == "copy":
        assert manager.download_file("source/report.txt") == b"report"
        assert not manager.exists("target/source/sub/data.txt")
    else:
        assert (
            sha256(manager.download_file("target/source/sub/data.txt")).digest()
            == sha256(b"data").digest()
        )
    assert (
        sha256(manager.download_file("target/source/report.txt")).digest()
        == sha256(b"report").digest()
    )

    client.copy_failure = None
    client.unconfirmed.clear()
    notifications.reset_mock()
    select_rows(browser, "source")
    asyncio.run(browser.handle_move_button_click())

    notifications.success.assert_called_once_with("Moved 1 items")
    notifications.error.assert_not_called()
    notifications.warning.assert_not_called()
    assert visible_paths(browser) == {"last.txt", "target"}
    assert manager.download_file("target/source/sub/data.txt") == b"data"
    assert manager.download_file("target/source/report.txt") == b"report"


@pytest.mark.parametrize("destination", [".", "../outside"])
def test_batch_move_rejects_invalid_destination(oss_browser, monkeypatch, destination):
    client, _, browser, notifications = oss_browser
    before = client.objects.copy()
    confirm_with(monkeypatch, table, "MoveDialog", Path(destination))
    select_rows(browser, "source")

    asyncio.run(browser.handle_move_button_click())

    notifications.error.assert_called_once()
    notifications.success.assert_not_called()
    assert client.objects == before


@pytest.mark.parametrize("action", ["move", "rename"])
def test_metadata_move_and_rename_report_partial_completion(
    oss_browser, monkeypatch, action
):
    client, manager, browser, notifications = oss_browser
    metadata = manager.get_file_metadata("source")
    target = SimpleNamespace(
        metadata=metadata,
        current_path=browser.current_path,
        file_manager=manager,
        refresh_browser=browser.refresh,
    )
    if action == "move":
        destination = "target/source"
        confirm_with(monkeypatch, dialog, "MoveDialog", Path("target"))
        callback = dialog.MetadataDialog.on_move_button_click
    else:
        destination = "renamed"
        confirm_with(monkeypatch, dialog, "RenameDialog", destination)
        callback = dialog.MetadataDialog.on_rename_button_click
    client.unconfirmed.add("users/synthetic/source/sub/data.txt")

    asyncio.run(callback(target))

    assert_partial_feedback(notifications)
    browser.refresh_func.refresh.assert_awaited_once()
    assert "source" in visible_paths(browser)
    assert manager.download_file("source/sub/data.txt") == b"data"
    assert not manager.exists("source/report.txt")
    assert manager.download_file(f"{destination}/report.txt") == b"report"
    assert manager.download_file(f"{destination}/sub/data.txt") == b"data"

    client.unconfirmed.clear()
    notifications.reset_mock()
    if action == "rename":
        # A confirmed copy blocks replacing the destination. Pick a new name
        # for the remaining source after checking the original destination.
        asyncio.run(callback(target))
        notifications.success.assert_not_called()
        notifications.warning.assert_called_once_with(
            "A file or folder with this name already exists."
        )
        notifications.reset_mock()
        confirm_with(monkeypatch, dialog, "RenameDialog", "remaining")
    asyncio.run(callback(target))

    notifications.success.assert_called_once()
    notifications.error.assert_not_called()
    notifications.warning.assert_not_called()
    assert "source" not in visible_paths(browser)
    assert manager.download_file(f"{destination}/sub/data.txt") == b"data"
    if action == "rename":
        assert manager.download_file("remaining/sub/data.txt") == b"data"
