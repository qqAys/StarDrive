import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.schemas.file_schema import DirMetadata, FileMetadata
from app.ui.components.table import FileBrowserTable


class FakeRefreshable:
    targets = [object()]

    def __init__(self):
        self.active = 0
        self.max_active = 0
        self.calls = 0

    async def refresh(self):
        self.calls += 1
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0)
        self.active -= 1


def test_refresh_serializes_concurrent_refreshable_calls():
    async def run_test():
        table = FileBrowserTable.__new__(FileBrowserTable)
        table.refresh_func = FakeRefreshable()
        table._refresh_lock = asyncio.Lock()

        await asyncio.gather(table.refresh(), table.refresh())

        assert table.refresh_func.calls == 2
        assert table.refresh_func.max_active == 1

    asyncio.run(run_test())


@pytest.fixture
def filter_table():
    table = FileBrowserTable.__new__(FileBrowserTable)
    table.name_filter = ""
    table.directory_rows = [
        {"raw_name": "Report.TXT", "path": "Report.TXT", "type": "file"},
        {"raw_name": "中文资料", "path": "中文资料", "type": "dir"},
        {"raw_name": "a[1]%.txt", "path": "a[1]%.txt", "type": "file"},
    ]
    table.browser_table = SimpleNamespace(
        rows=list(table.directory_rows),
        selected=list(table.directory_rows),
        pagination={"page": 8, "rowsPerPage": 15, "sortBy": "raw_name"},
        update=Mock(),
    )
    table.footer_container = Mock()
    table.is_select_mode = True
    return table


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("", ["Report.TXT", "中文资料", "a[1]%.txt"]),
        (None, ["Report.TXT", "中文资料", "a[1]%.txt"]),
        ("rEpOrT", ["Report.TXT"]),
        ("资料", ["中文资料"]),
        ("[1]%", ["a[1]%.txt"]),
        ("missing", []),
    ],
)
def test_filter_change_updates_rows_selection_and_page(filter_table, query, expected):
    asyncio.run(filter_table.handle_name_filter_change(SimpleNamespace(value=query)))

    assert [row["raw_name"] for row in filter_table.browser_table.rows] == expected
    assert filter_table.browser_table.selected == filter_table.browser_table.rows
    assert filter_table.browser_table.pagination == {
        "page": 1,
        "rowsPerPage": 15,
        "sortBy": "raw_name",
    }
    filter_table.footer_container.clear.assert_called_once()
    filter_table.browser_table.update.assert_called_once()


def test_clear_restores_rows_without_hidden_selection(filter_table):
    async def run_test():
        await filter_table.handle_name_filter_change(SimpleNamespace(value="资料"))
        await filter_table.handle_name_filter_change(SimpleNamespace(value=None))

    asyncio.run(run_test())
    assert filter_table.browser_table.rows == filter_table.directory_rows
    assert filter_table.browser_table.selected == [filter_table.directory_rows[1]]


def test_navigation_resets_filter_but_same_directory_preserves_it(
    filter_table, monkeypatch
):
    save_path = Mock()
    monkeypatch.setattr("app.ui.components.table.set_user_last_path", save_path)
    filter_table._current_path = Path("docs")
    filter_table.name_filter = "report"
    filter_table.current_path = Path("docs")
    assert filter_table.name_filter == "report"
    filter_table.refresh = AsyncMock()
    asyncio.run(filter_table.goto_func(Path("other")))
    assert filter_table.name_filter == ""
    save_path.assert_called_once_with(Path("other"))
    filter_table.refresh.assert_awaited_once()


def test_hidden_mouse_row_and_empty_enter_are_ignored(filter_table):
    hidden = filter_table.directory_rows[0]

    async def run_test():
        await filter_table.handle_name_filter_change(SimpleNamespace(value="missing"))
        await filter_table.handle_row_click(SimpleNamespace(args=[None, hidden, 0]))
        filter_table.is_select_mode = False
        await filter_table.handle_row_double_click(None, from_keyboard=True)
        await filter_table.handle_row_double_click(
            SimpleNamespace(args=[None, hidden, 0])
        )

    asyncio.run(run_test())
    assert filter_table.browser_table.selected == []


def test_keyboard_moves_only_among_filtered_rows(filter_table, monkeypatch):
    monkeypatch.setattr(
        "app.ui.components.table.ui.run_javascript",
        AsyncMock(return_value=["Report.TXT", "中文资料", "a[1]%.txt"]),
    )
    monkeypatch.setattr(
        "app.ui.components.table.app",
        SimpleNamespace(storage=SimpleNamespace(client={})),
    )
    filter_table._scroll_dom_row_into_view = AsyncMock()
    filter_table.handle_row_click = AsyncMock()

    async def run_test():
        await filter_table.handle_name_filter_change(SimpleNamespace(value="资料"))
        filter_table.browser_table.selected = []
        await filter_table.handle_keyboard_arrow_event("down")

    asyncio.run(run_test())
    event = filter_table.handle_row_click.await_args.args[0]
    assert event.args[1]["raw_name"] == "中文资料"
    filter_table._scroll_dom_row_into_view.assert_awaited_once_with(0)


@pytest.mark.parametrize("prefix", ["local/docs", "oss-prefix/users/sample/docs"])
def test_metadata_rows_share_name_matching(filter_table, prefix):
    metadata = [
        FileMetadata(name="Report.TXT", path=f"{prefix}/Report.TXT"),
        DirMetadata(name="中文资料", path=f"{prefix}/中文资料"),
    ]
    filter_table.directory_rows = [
        {"raw_name": item.name, "path": item.path, "type": item.type}
        for item in metadata
    ]
    asyncio.run(filter_table.handle_name_filter_change(SimpleNamespace(value="REPORT")))
    assert filter_table.browser_table.rows == [filter_table.directory_rows[0]]


@pytest.fixture
def preview_table(filter_table, monkeypatch):
    filter_table.is_select_mode = False
    filter_table.has_dialog_open = False
    filter_table.file_manager = Mock(
        backend_name="LocalStorage", user_id="isolated-user"
    )
    storage = SimpleNamespace(user={"user_id": "isolated-user"})
    app = SimpleNamespace(storage=storage)
    user_manager = SimpleNamespace(
        current_user=AsyncMock(return_value=SimpleNamespace(is_active=True))
    )
    monkeypatch.setattr("app.security.guards.app", app)
    monkeypatch.setattr(
        "app.security.guards.globals.get_user_manager", lambda: user_manager
    )
    monkeypatch.setattr("app.security.guards.navigate_to", Mock())
    monkeypatch.setattr("app.ui.components.table.app", app)
    dialog = Mock()
    dialog.return_value.open = AsyncMock()
    monkeypatch.setattr("app.ui.components.table.MediaDialog", dialog)
    monkeypatch.setattr("app.ui.components.table.notify.error", Mock())
    return filter_table, dialog


async def click_preview(table, args):
    await table.handle_preview_button_click(SimpleNamespace(args=args))


@pytest.mark.parametrize("session", [{}, {"user_id": "other-user"}])
def test_preview_rejects_stale_page_after_session_change(preview_table, session):
    from app.ui.components.table import app

    table, dialog = preview_table
    table.browser_table.selected = [table.directory_rows[0]]
    app.storage.user = session

    async def run_test():
        await click_preview(table, {"path": "Report.TXT"})
        await table.handle_keyboard_space_event()

    asyncio.run(run_test())
    dialog.assert_not_called()


@pytest.mark.parametrize("backend", ["LocalStorage", "AliyunOSSStorage"])
def test_preview_button_uses_visible_path_and_existing_user_manager(
    preview_table, backend
):
    table, dialog = preview_table
    table.file_manager.backend_name = backend
    table.file_manager.user_id = "isolated-user"
    table.browser_table.selected = [table.directory_rows[1]]
    selected = list(table.browser_table.selected)
    asyncio.run(click_preview(table, {"path": "Report.TXT", "type": "dir"}))
    dialog.assert_called_once_with(table.file_manager, Path("Report.TXT"))
    dialog.return_value.open.assert_awaited_once()
    assert table.browser_table.selected == selected
    assert table.has_dialog_open is False


@pytest.mark.parametrize(
    "args",
    [
        {},
        None,
        [],
        {"path": None},
        {"path": []},
        {"path": ""},
        {"path": "missing.txt"},
        {"path": "../other-user/private.txt"},
        {"path": "中文资料", "type": "file"},
    ],
)
def test_preview_rejects_missing_forged_and_directory_targets(preview_table, args):
    table, dialog = preview_table
    asyncio.run(click_preview(table, args))
    dialog.assert_not_called()
    assert table.has_dialog_open is False


def test_preview_rejects_hidden_target_and_select_mode(preview_table):
    table, dialog = preview_table

    async def run_test():
        await table.handle_name_filter_change(SimpleNamespace(value="资料"))
        await click_preview(table, {"path": "Report.TXT"})
        await table.handle_name_filter_change(SimpleNamespace(value=""))
        table.is_select_mode = True
        await click_preview(table, {"path": "Report.TXT"})

    asyncio.run(run_test())
    dialog.assert_not_called()


def test_preview_click_and_space_share_guard_and_allow_reopening(preview_table):
    table, dialog = preview_table

    async def run_test():
        entered = asyncio.Event()
        closed = asyncio.Event()

        async def open_dialog():
            entered.set()
            await closed.wait()

        dialog.return_value.open.side_effect = open_dialog
        table.browser_table.selected = [table.directory_rows[0]]
        opening = asyncio.create_task(click_preview(table, {"path": "Report.TXT"}))
        await entered.wait()
        assert table.has_dialog_open is True
        await click_preview(table, {"path": "Report.TXT"})
        await table.handle_keyboard_space_event()
        dialog.assert_called_once()
        closed.set()
        await opening
        await table.handle_keyboard_space_event()

    asyncio.run(run_test())
    assert dialog.call_count == 2
    assert table.has_dialog_open is False


@pytest.mark.parametrize("failure", ["construct", "open"])
def test_preview_failure_restores_guard_and_reports_existing_error(
    preview_table, failure, monkeypatch
):
    table, dialog = preview_table
    error = Mock()
    monkeypatch.setattr("app.ui.components.table.notify.error", error)
    if failure == "construct":
        dialog.side_effect = RuntimeError("preview unavailable")
    else:
        dialog.return_value.open.side_effect = RuntimeError("preview unavailable")
    asyncio.run(click_preview(table, {"path": "Report.TXT"}))
    assert table.has_dialog_open is False
    error.assert_called_once()
    assert "preview unavailable" in error.call_args.args[0]
    dialog.side_effect = None
    dialog.return_value.open.side_effect = None
    asyncio.run(click_preview(table, {"path": "Report.TXT"}))
    assert dialog.call_count == 2
    assert table.has_dialog_open is False


def test_preview_slot_wires_accessible_button_and_stops_row_events():
    import inspect

    source = inspect.getsource(FileBrowserTable.__init__)
    button = next(line for line in source.splitlines() if 'icon="visibility"' in line)
    assert "v-if=\"props.row.type === 'file'\"" in button
    assert "aria-label=" in button
    assert "@click.stop=\"$parent.$emit('preview'," in button
    assert "@dblclick.stop" in button
    assert "@keydown.stop" in button
    assert "@keyup.stop" in button
    assert (
        "if self.is_select_mode:\n                columns.remove(self.action_column)"
        in source
    )
    assert (
        'self.browser_table.on("preview", self.handle_preview_button_click)' in source
    )


def test_space_preview_rejects_stale_selection_and_directory(preview_table):
    table, dialog = preview_table

    async def run_test():
        for selected in ([], [table.directory_rows[1]], [{"path": "hidden.txt"}]):
            table.browser_table.selected = selected
            await table.handle_keyboard_space_event()

    asyncio.run(run_test())
    dialog.assert_not_called()


def test_double_click_still_opens_download_confirmation(preview_table, monkeypatch):
    table, preview = preview_table
    confirm = Mock()
    confirm.return_value.open = AsyncMock(return_value=False)
    monkeypatch.setattr("app.ui.components.table.ConfirmDialog", confirm)
    asyncio.run(
        table.handle_row_double_click(
            SimpleNamespace(args=[None, table.directory_rows[0], 0])
        )
    )
    confirm.return_value.open.assert_awaited_once()
    preview.assert_not_called()


@pytest.mark.parametrize("kind, count", [("all", 61), ("file", 60), ("dir", 1)])
def test_type_filter_full_directory_resets_page_and_selection(
    filter_table, kind, count
):
    filter_table.directory_rows = [
        {"raw_name": f"report-{index}", "path": f"report-{index}", "type": "file"}
        for index in range(60)
    ] + [{"raw_name": "reports", "path": "reports", "type": "dir"}]
    filter_table.file_manager = Mock()
    asyncio.run(filter_table.handle_type_filter_change(SimpleNamespace(value=kind)))
    assert len(filter_table.browser_table.rows) == count
    assert filter_table.browser_table.selected == []
    assert filter_table.browser_table.pagination["page"] == 1
    filter_table.file_manager.assert_not_called()
    assert filter_table.file_manager.mock_calls == []


def test_type_filter_combines_name_and_resets_controls(filter_table):
    filter_table.search_input = SimpleNamespace(set_value=Mock())
    filter_table.type_filter_input = SimpleNamespace(set_value=Mock())

    async def run_test():
        await filter_table.handle_type_filter_change(SimpleNamespace(value="file"))
        await filter_table.handle_name_filter_change(SimpleNamespace(value="资料"))
        assert filter_table.browser_table.rows == []
        await filter_table.reset_filters()

    asyncio.run(run_test())
    assert filter_table.browser_table.rows == filter_table.directory_rows
    assert filter_table.browser_table.selected == []
    assert filter_table.name_filter == ""
    assert filter_table.type_filter == "all"
    filter_table.search_input.set_value.assert_called_once_with("")
    filter_table.type_filter_input.set_value.assert_called_once_with("all")


def test_empty_type_results_ignore_keyboard(filter_table, monkeypatch):
    monkeypatch.setattr(
        "app.ui.components.table.ui.run_javascript", AsyncMock(return_value=[])
    )
    preview = Mock()
    monkeypatch.setattr("app.ui.components.table.MediaDialog", preview)
    filter_table.has_dialog_open = False
    filter_table.is_select_mode = False

    async def run_test():
        await filter_table.handle_type_filter_change(SimpleNamespace(value="dir"))
        await filter_table.handle_name_filter_change(SimpleNamespace(value="missing"))
        await filter_table.handle_row_double_click(None, from_keyboard=True)
        await filter_table.handle_keyboard_space_event()
        await filter_table.handle_keyboard_arrow_event("up")
        await filter_table.handle_keyboard_arrow_event("down")

    asyncio.run(run_test())
    preview.assert_not_called()
    assert filter_table.browser_table.selected == []


def test_type_filter_resets_on_navigation(filter_table, monkeypatch):
    monkeypatch.setattr("app.ui.components.table.set_user_last_path", Mock())
    filter_table._current_path = Path("docs")
    filter_table.type_filter = "dir"
    filter_table.current_path = Path("docs")
    assert filter_table.type_filter == "dir"
    filter_table.current_path = Path("other")
    assert filter_table.type_filter == "all"


def test_invalid_type_selection_restores_all(filter_table):
    asyncio.run(filter_table.handle_type_filter_change(SimpleNamespace(value=None)))
    assert filter_table.type_filter == "all"
    assert filter_table.browser_table.rows == filter_table.directory_rows
