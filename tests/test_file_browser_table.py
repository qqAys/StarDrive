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
