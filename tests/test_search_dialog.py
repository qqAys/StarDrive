"""Controlled asynchronous backends; no deployment, database or real files."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ui.components import dialog


def make_search(monkeypatch):
    monkeypatch.setattr(dialog, "ui", MagicMock())
    target = dialog.SearchDialog.__new__(dialog.SearchDialog)
    target.file_manager = SimpleNamespace(search=AsyncMock(return_value=[]))
    target.current_path = Path("synthetic-user-a")
    target.dialog = MagicMock()
    target.client = MagicMock()
    target.results_list = MagicMock()
    target.status = MagicMock()
    target.retry = MagicMock()
    target.search_input = SimpleNamespace(value="A")
    target.search_task = None
    target.generation = 0
    target.active = True
    target.suspended = False
    target.disposed = False
    target.loading = False
    target.last_query = "A"
    target.offset = 0
    target.has_more = True
    return target


def test_late_cancelled_result_cannot_change_new_query(monkeypatch):
    target = make_search(monkeypatch)

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        async def backend(**kwargs):
            if kwargs["query"] == "A":
                entered.set()
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    await release.wait()  # simulate a cancellation-resistant backend
                return [SimpleNamespace(name="stale", path="stale")]
            return []

        target.file_manager.search.side_effect = backend
        old = asyncio.create_task(target.load_more())
        await entered.wait()
        target.search_input.value = "B"
        await target.on_input_change()
        current = target.search_task
        await current
        release.set()
        await old
        assert target.last_query == "B"
        assert target.offset == 0
        assert not target.loading
        assert not target.has_more
        dialog.ui.item.assert_not_called()

    asyncio.run(scenario())


def test_disconnect_cancels_and_reconnect_retries_current_page(monkeypatch):
    target = make_search(monkeypatch)
    target.offset = 30

    async def scenario():
        entered = asyncio.Event()

        async def backend(**kwargs):
            entered.set()
            await asyncio.Event().wait()

        target.file_manager.search.side_effect = backend
        pending = asyncio.create_task(target.load_more())
        await entered.wait()
        target.pause_search()
        await asyncio.gather(pending, return_exceptions=True)
        assert target.active and target.suspended
        await target.load_more()
        assert target.file_manager.search.await_count == 1
        target.file_manager.search.side_effect = None
        await target.resume_search()
        assert not target.loading and not target.suspended
        assert [
            c.kwargs["offset"] for c in target.file_manager.search.await_args_list
        ] == [30, 30]
        target.close_search()
        await target.resume_search()
        assert target.file_manager.search.await_count == 2

    asyncio.run(scenario())


@pytest.mark.parametrize("old_fails", [False, True])
def test_stale_completion_cannot_release_current_loading(monkeypatch, old_fails):
    """Old success and failure must not change a still-running replacement page."""
    target = make_search(monkeypatch)

    async def scenario():
        old_entered, old_release = asyncio.Event(), asyncio.Event()
        new_entered, new_release = asyncio.Event(), asyncio.Event()

        async def backend(**kwargs):
            if kwargs["query"] == "A":
                old_entered.set()
                try:
                    await old_release.wait()
                except asyncio.CancelledError:
                    await old_release.wait()
                if old_fails:
                    raise RuntimeError("synthetic stale failure")
                return [SimpleNamespace(name="stale", path="stale")]
            new_entered.set()
            await new_release.wait()
            return []

        target.file_manager.search.side_effect = backend
        old = asyncio.create_task(target.load_more())
        await old_entered.wait()
        target.search_input.value = "B"
        await target.on_input_change()
        current = target.search_task
        await new_entered.wait()
        target.status.reset_mock()
        target.retry.reset_mock()
        old_release.set()
        await old
        assert target.loading
        assert target.search_task is current
        assert target.offset == 0 and target.has_more
        target.status.set_text.assert_not_called()
        target.retry.set_visibility.assert_not_called()
        dialog.ui.item.assert_not_called()
        await target.load_more()  # scroll/retry cannot start a duplicate page
        assert target.file_manager.search.await_count == 2
        new_release.set()
        await current
        assert not target.loading and target.search_task is None
        assert not target.has_more

    asyncio.run(scenario())


def test_real_components_open_hide_reopen_and_safe_names(monkeypatch):
    """Exercise native component construction and dialog await/finally, without a browser."""
    from nicegui import Client, ui

    monkeypatch.setattr(dialog, "_", lambda text: text)
    monkeypatch.setattr(dialog, "get_file_icon", lambda *_: "")

    async def scenario():
        monkeypatch.setattr("nicegui.core.loop", asyncio.get_running_loop())
        with (
            Client(ui.page("/search-components-test")) as client,
            ui.column() as container,
        ):
            target = dialog.SearchDialog(
                SimpleNamespace(search=AsyncMock(return_value=[])), Path("/")
            )
        try:
            opening = asyncio.create_task(target.open())
            await asyncio.sleep(0)
            assert target.dialog.value and target.active
            assert target.search_input._props["autofocus"] is True
            name = '<img src=x onerror=alert(1)> & "report"'
            item = SimpleNamespace(name=name, path=Path(name), type=None, extension="")
            target.last_query = "report"
            target.file_manager.search.return_value = [item]
            await target.load_more()
            descendants = list(target.results_list.descendants())
            rendered = [
                element.content
                for element in descendants
                if isinstance(element, ui.html)
            ]
            assert rendered == [f" <b>{dialog.html.escape(name)}</b>"]
            assert any(
                isinstance(element, ui.label) and element.text == name
                for element in descendants
            )
            target.has_more = True
            target.file_manager.search.return_value = []
            target.pause_search()
            assert target.dialog.value and target.active
            await target.resume_search()
            assert target.file_manager.search.await_args.kwargs["offset"] == 1
            assert target.active and not target.loading
            # Invoke the registered native hide handler, then let the actual await finish.
            hide = next(
                listener
                for listener in target.dialog._event_listeners.values()
                if listener.type == "hide"
            )
            hide.handler()
            assert not target.active
            target.dialog.submit(item)
            assert await opening is item
            assert not target.active and target.search_task is None
            reopened = asyncio.create_task(target.open())
            await asyncio.sleep(0)
            assert target.active and target.last_query is None and target.offset == 0
            assert not list(target.results_list.descendants())
            target.dialog.submit(None)
            assert await reopened is None
            assert not target.active
        finally:
            target.dispose()
            container.delete()
            client.delete()

    asyncio.run(scenario())


def test_local_search_user_roots_pagination_and_traversal(tmp_path):
    import pytest
    from app.services.file_service import StorageManager
    from app.storage.base import StoragePermissionError
    from app.storage.local_storage import LocalStorage

    async def scenario():
        managers = []
        for user in ("user-a", "user-b"):
            root = tmp_path / user
            root.mkdir()
            (root / "nested").mkdir()
            for index in range(100):
                (root / "nested" / f"match-{user}-{index:03}.txt").write_text(user)
            (root / "nested" / 'match-<b>&".txt').write_text(user)
            manager = StorageManager(root)
            manager.set_current_backend(LocalStorage.name)
            managers.append(manager)
        for user, manager in zip(("user-a", "user-b"), managers):
            results = []
            for offset in (0, 30, 60, 90):
                results.extend(await manager.search("match", "/", offset, 30))
            assert len(results) == 101
            assert len({str(item.path) for item in results}) == 101
            assert all(
                manager.get_full_path(str(item.path)).read_text() == user
                for item in results
            )
            assert any(item.name == 'match-<b>&".txt' for item in results)
            with pytest.raises(StoragePermissionError):
                await manager.search("match", "../", 0, 30)

    asyncio.run(scenario())


def test_page_failure_retries_same_offset_once(monkeypatch):
    target = make_search(monkeypatch)
    target.offset = 30
    target.file_manager.search.side_effect = [RuntimeError("synthetic"), []]

    async def scenario():
        await target.load_more()
        assert target.offset == 30
        assert not target.loading
        assert target.has_more
        target.retry.set_visibility.assert_called_with(True)
        await target.load_more()
        assert target.offset == 30
        assert not target.has_more
        assert [
            call.kwargs["offset"] for call in target.file_manager.search.await_args_list
        ] == [30, 30]

    asyncio.run(scenario())


def test_clear_close_and_other_client_are_independent(monkeypatch):
    first, second = make_search(monkeypatch), make_search(monkeypatch)

    async def scenario():
        first.last_query = None
        await first.on_input_change()
        pending = first.search_task
        first.search_input.value = ""
        await first.on_input_change()
        await asyncio.gather(pending, return_exceptions=True)
        assert first.search_task is None
        assert not first.loading
        first.file_manager.search.assert_not_awaited()
        first.close_search()
        await first.load_more()
        await second.load_more()
        second.file_manager.search.assert_awaited_once()
        assert second.active
        assert not first.active

    asyncio.run(scenario())


def test_cancel_inflight_releases_loading_and_reopen_can_search(monkeypatch):
    target = make_search(monkeypatch)

    async def scenario():
        entered = asyncio.Event()

        async def backend(**kwargs):
            entered.set()
            await asyncio.Event().wait()

        target.file_manager.search.side_effect = backend
        task = asyncio.create_task(target.load_more())
        await entered.wait()
        target.close_search()
        await asyncio.gather(task, return_exceptions=True)
        assert not target.loading
        assert target.search_task is None
        target.active = True
        target.last_query = None
        target.file_manager.search.side_effect = None
        await target.on_input_change()
        await target.search_task
        assert not target.loading
        assert target.offset == 0

    asyncio.run(scenario())


def test_successful_pages_and_initial_failure(monkeypatch):
    target = make_search(monkeypatch)
    items = [
        SimpleNamespace(
            name=f"match-{i}",
            path=f"synthetic-user-a/match-{i}",
            type=None,
            extension="",
        )
        for i in range(100)
    ]
    monkeypatch.setattr(dialog, "get_file_icon", lambda *_: "")

    async def backend(**kwargs):
        start = kwargs["offset"]
        return items[start : start + kwargs["limit"]]

    async def scenario():
        target.file_manager.search.side_effect = RuntimeError(
            "synthetic initial failure"
        )
        await target.load_more()
        assert target.offset == 0
        assert target.has_more
        assert not target.loading
        target.file_manager.search.side_effect = backend
        for expected in (30, 60, 90, 100):
            await target.load_more()
            assert target.offset == expected
        assert not target.has_more
        assert dialog.ui.item.call_count == 100
        await target.load_more()
        assert dialog.ui.item.call_count == 100
        callbacks = [call.kwargs["on_click"] for call in dialog.ui.item.call_args_list]
        callbacks[-1]()
        target.dialog.submit.assert_called_once_with(items[-1])

    asyncio.run(scenario())


def test_file_browser_search_entry_releases_each_dialog(monkeypatch):
    """Use the real entry body and native components for repeated one-shot dialogs."""
    import gc
    import weakref

    from nicegui import Client, ui
    from app.ui.components import table

    monkeypatch.setattr(dialog, "_", lambda text: text)
    created = []

    def create_search(*args):
        target = dialog.SearchDialog(*args)
        created.append(target)
        return target

    monkeypatch.setattr(table, "SearchDialog", create_search)

    async def scenario():
        monkeypatch.setattr("nicegui.core.loop", asyncio.get_running_loop())
        with Client(ui.page("/search-entry-test")) as client, ui.column() as container:
            client = container.client
            browser = SimpleNamespace(
                file_manager=SimpleNamespace(search=AsyncMock(return_value=[])),
                current_path=Path("/"),
                refresh=AsyncMock(),
            )
            entry = table.FileBrowserTable.handle_search_button_click.__wrapped__
            element_count = len(client.elements)
            connections = list(client.connect_handlers)
            disconnections = list(client.disconnect_handlers)
            references = []

            async def open_in_client_slot():
                # NiceGUI event dispatch supplies the originating client slot;
                # an asyncio background task does not inherit that slot stack.
                with container:
                    await entry(browser)

            for index in range(20):
                opening = asyncio.create_task(open_in_client_slot())
                await asyncio.sleep(0)
                target = created.pop()
                references.append(weakref.ref(target))
                assert target.active
                assert len(client.connect_handlers) == len(connections) + 1
                assert len(client.disconnect_handlers) == len(disconnections) + 1
                if index % 2:
                    opening.cancel()  # page callback cancellation also releases resources
                    await asyncio.gather(opening, return_exceptions=True)
                else:
                    target.dialog.submit(None)
                    await opening
                assert target.disposed and not target.active
                assert target.search_task is None
                assert target.dialog.is_deleted
                assert len(client.elements) == element_count
                assert client.connect_handlers == connections
                assert client.disconnect_handlers == disconnections
                generation = target.generation
                target.pause_search()
                await target.resume_search()
                assert target.generation == generation
                browser.file_manager.search.assert_not_awaited()
                target.dispose()  # idempotent cleanup
                del target, opening
            browser.refresh.assert_not_awaited()
            await asyncio.sleep(0)
            gc.collect()
            assert all(reference() is None for reference in references)
        container.delete()
        client.delete()

    asyncio.run(scenario())


def test_dispose_after_client_deletion_removes_callbacks(monkeypatch):
    from nicegui import Client, ui

    monkeypatch.setattr(dialog, "_", lambda text: text)

    async def scenario():
        with Client(ui.page("/search-deleted-client-test")) as client:
            target = dialog.SearchDialog(SimpleNamespace(search=AsyncMock()), Path("/"))
        client.delete()
        target.dispose()
        target.dispose()
        assert target.disposed
        assert not client.connect_handlers
        assert not client.disconnect_handlers
        assert target.dialog.is_deleted
        assert target.lifecycle_container.is_deleted

    asyncio.run(scenario())


@pytest.mark.parametrize("is_dir", [False, True])
def test_search_entry_disposes_before_result_navigation(monkeypatch, is_dir):
    """Cleanup must preserve the existing file and directory navigation contract."""
    from app.ui.components import table

    result = SimpleNamespace(path="/nested/match", is_dir=is_dir)
    search = SimpleNamespace(open=AsyncMock(return_value=result), dispose=MagicMock())
    monkeypatch.setattr(table, "SearchDialog", lambda *_: search)
    browser = SimpleNamespace(file_manager=object(), current_path=Path("/"))

    async def refresh():
        search.dispose.assert_called_once_with()
        assert browser.current_path == Path("/nested/match" if is_dir else "/nested")
        if not is_dir:
            assert browser.pending_display_metadata_path == "/nested/match"

    browser.refresh = AsyncMock(side_effect=refresh)
    asyncio.run(table.FileBrowserTable.handle_search_button_click.__wrapped__(browser))
    browser.refresh.assert_awaited_once()


def test_search_entry_releases_dialog_when_open_fails(monkeypatch):
    from app.ui.components import table

    search = SimpleNamespace(
        open=AsyncMock(side_effect=RuntimeError("synthetic open failure")),
        dispose=MagicMock(),
    )
    monkeypatch.setattr(table, "SearchDialog", lambda *_: search)
    browser = SimpleNamespace(
        file_manager=object(), current_path=Path("/"), refresh=AsyncMock()
    )
    with pytest.raises(RuntimeError, match="synthetic open failure"):
        asyncio.run(
            table.FileBrowserTable.handle_search_button_click.__wrapped__(browser)
        )
    search.dispose.assert_called_once_with()
    browser.refresh.assert_not_awaited()
    assert browser.current_path == Path("/")


def test_reconnect_javascript_tracks_latest_sequence_and_unregisters():
    """Execute the emitted script; browser outage evidence covers Socket.IO itself."""
    import json
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to execute the reconnect JavaScript contract")
    target = dialog.SearchDialog.__new__(dialog.SearchDialog)
    target.client = MagicMock()
    target.reconnect_key = 'search-dialog-"synthetic"'
    scripts = []
    for install in (True, True, False, False):
        target._update_reconnect_handler(install=install)
        scripts.append(target.client.run_javascript.call_args.args[0])
    # Check repeated installation, live sequence reads, idempotent removal and
    # preservation of unrelated listeners/query fields rather than script text.
    harness = r"""
const assert = require('node:assert/strict');
const {EventEmitter} = require('node:events');
const scripts = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const manager = new EventEmitter();
manager.opts = {query: {next_message_id: 0, client_id: 'synthetic-client'}};
global.window = {socket: {io: manager}, nextMessageId: 17};
let unrelatedCalls = 0;
const unrelated = () => unrelatedCalls++;
manager.on('reconnect_attempt', unrelated);
for (const script of scripts.slice(0, 2)) {
    eval(script);
    assert.equal(manager.listenerCount('reconnect_attempt'), 2);
    assert.equal(Object.keys(manager.stardriveSearchHandlers).length, 1);
}
manager.emit('reconnect_attempt');
assert.equal(manager.opts.query.next_message_id, 17);
window.nextMessageId = 42;
manager.emit('reconnect_attempt');
assert.equal(manager.opts.query.next_message_id, 42);
assert.equal(manager.opts.query.client_id, 'synthetic-client');
for (const script of scripts.slice(2)) {
    eval(script);
    assert.equal(manager.listenerCount('reconnect_attempt'), 1);
    assert.equal(Object.keys(manager.stardriveSearchHandlers).length, 0);
}
window.nextMessageId = 99;
manager.emit('reconnect_attempt');
assert.equal(manager.opts.query.next_message_id, 42);
assert.equal(unrelatedCalls, 3);
// Closing a disconnected page must also be harmless.
window.socket = undefined;
for (const script of scripts) eval(script);
"""
    subprocess.run(
        [node, "-e", harness],
        input=json.dumps(scripts),
        text=True,
        capture_output=True,
        check=True,
        timeout=10,
    )
