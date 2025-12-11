import asyncio
from pathlib import Path

from fastapi.responses import RedirectResponse
from nicegui import events, ui, APIRouter, app
from nicegui.elements.table import Table

import globals
from ui.components.base import base_layout
from ui.components.dialog import AskDialog
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
        nonlocal file_list
        file_list = M.list_files(current_path)

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
                "name": "name",
                "label": _("Name"),
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
            {
                "name": "action",
                "label": _("Action"),
                "align": "center",
            },
        ]
        browser_table = ui.table(
            columns=columns,
            rows=[],
            row_key="file",
            title=_("File List"),
            pagination=0,
            column_defaults={"align": "left"},
        ).classes("w-full h-full")

        browser_table.pagination = {
            "sortBy": None,
            "descending": False,
            "page": 1,
            "rowsPerPage": 0 if len(file_list) < 50 else 15,
        }

        async def back_func():
            nonlocal file_list, current_path
            if current_path == ".":
                notify.warning(_("You are already at the root directory"))
                return
            current_path = Path(current_path).parent.__str__()
            await browser.refresh()

        add_table_controls(browser_table, show_path=current_path, back_func=back_func)
        browser_table.add_slot(
            "body-cell-name", '<q-td v-html="props.row.name"></q-td>'
        )
        browser_table.add_slot(
            "body-cell-action",
            f"""
    <q-td :props="props">
        <q-btn flat dense round icon="share" @click="() => $parent.$emit('share', props.row)" />
        <q-btn flat dense round icon="delete" @click="() => $parent.$emit('delete', props.row)" />
        <q-btn flat dense round icon="download" @click="() => $parent.$emit('download', props.row)" />
        <q-btn flat dense round icon="edit_document" @click="() => $parent.$emit('rename', props.row)" />
        <q-btn flat dense round icon="drive_file_move" @click="() => $parent.$emit('move', props.row)" />
    </q-td>
""",
        )

        browser_table.rows = [
            {
                "name": f"📁 <b>{p.name}</b>" if p.type == "dir" else p.name,
                "raw_name": p.name,
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

        async def handle_row_double_click(e: events.GenericEventArguments):
            nonlocal file_list, current_path
            click_event_params, click_row, click_index = e.args
            target_path = click_row["path"]

            if click_row["type"] == "dir":
                current_path = target_path
                await browser.refresh()
            else:
                ui.download.content(M.download_file(target_path), click_row["name"])

        async def handle_action_click(action, e: events.GenericEventArguments):
            click_row = e.args

            click_name = click_row["raw_name"]
            click_path = click_row["path"]
            click_type = click_row["type"]

            if action == "delete":
                confirm = await AskDialog(
                    title=(
                        _("Delete file") if click_type == "file" else _("Delete folder")
                    ),
                    message=_("Are you sure you want to delete {}?").format(click_name),
                    warning=True,
                ).open()
                if confirm:
                    try:
                        if click_type == "dir":
                            M.delete_directory(click_path)
                        else:
                            M.delete_file(click_path)
                        notify.success(_("Successfully deleted {}").format(click_name))
                    except Exception as e:
                        notify.error(e)
                else:
                    return

            await asyncio.sleep(0.2)
            await browser.refresh()

        browser_table.on("row-dblclick", handle_row_double_click)
        browser_table.on("delete", lambda e: handle_action_click("delete", e))

        return browser_table

    await browser()
    file_list = M.list_files(current_path)
    await browser.refresh()
