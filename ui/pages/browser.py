from pathlib import Path

from fastapi.responses import RedirectResponse
from nicegui import events, ui, APIRouter, app
from nicegui.elements.table import Table

import globals
from ui.components.base import base_layout
from ui.components.notify import notify
from ui.components.table import add_table_controls
from utils import bytes_to_human_readable, _, timestamp_to_human_readable

this_page_routes = "/home"


@app.get("/")
def index():
    return RedirectResponse(this_page_routes + "/")


@app.get(this_page_routes)
def browser_index():
    return RedirectResponse(this_page_routes + "/")


router = APIRouter(prefix=this_page_routes)


@router.page("/")
@base_layout(header=True, footer=True, args={"title": _("Home")})
async def index():
    multiple = True
    M = globals.get_storage_manager()

    file_list = []
    current_path = "."

    @ui.refreshable
    async def browser() -> Table:

        size_sort_js = """(a, b, rowA, rowB) => {
            const isDirA = rowA.type === 'dir';
            const isDirB = rowB.type === 'dir';

            // 目录优先
            if (isDirA && !isDirB) return -1;
            if (!isDirA && isDirB) return 1;

            // 按 raw_size 排序
            return rowA.raw_size - rowB.raw_size;
        }"""

        columns = [
            {
                "name": "file",
                "label": _("File"),
                "field": "name",
                "align": "left",
                "required": True,
                "sortable": True,
            },
            {
                "name": "size",
                "label": _("Size"),
                "field": "size",
                "align": "right",
                "required": True,
                "sortable": True,
                ":sort": size_sort_js,
            },
            {
                "name": "created_at",
                "label": _("Created At"),
                "field": "created_at",
                "sortable": True,
            },
            {
                "name": "updated_at",
                "label": _("Updated At"),
                "field": "updated_at",
                "sortable": True,
            },
        ]
        browser_table = ui.table(
            columns=columns,
            rows=[],
            row_key="file",
            title=_("File List"),
        ).classes("w-full h-full")

        async def back_func():
            nonlocal file_list, current_path
            if current_path == ".":
                notify.warning(_("You are already at the root directory"))
                return
            current_path = Path(current_path).parent.__str__()
            file_list = M.list_files(current_path)
            await browser.refresh()

        add_table_controls(browser_table, show_path=current_path, back_func=back_func)

        browser_table.rows = [
            {
                "name": f"📁 {p.name}" if p.type == "dir" else p.name,
                "type": p.type,
                "path": p.path,
                "size": bytes_to_human_readable(p.size) if p.size else "-",
                "raw_size": p.size if p.size else -1,
                "created_at": (
                    timestamp_to_human_readable(p.created_at) if p.created_at else "-"
                ),
                "updated_at": (
                    timestamp_to_human_readable(p.updated_at) if p.updated_at else "-"
                ),
            }
            for p in file_list
        ]

        async def handle_row_click(e: events.GenericEventArguments):
            nonlocal file_list, current_path
            click_event_params, click_row, click_index = e.args
            target_path = click_row["path"]

            if click_row["type"] == "dir":
                file_list = M.list_files(target_path)
                current_path = target_path
                await browser.refresh()
            else:
                ui.download.content(M.download_file(target_path), click_row["name"])

        browser_table.on("row-dblclick", handle_row_click)

        return browser_table

    def switch_lang():
        lang_code = app.storage.user.get("default_lang", "en_US")
        if lang_code == "en_US":
            lang_code = "zh_CN"
        else:
            lang_code = "en_US"
        app.storage.user["default_lang"] = lang_code
        ui.navigate.to(this_page_routes)

    ui.button("切换语言", on_click=switch_lang)

    await browser()
    file_list = M.list_files(current_path)
    await browser.refresh()
