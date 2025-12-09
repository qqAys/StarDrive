from pathlib import Path

from fastapi.responses import RedirectResponse
from nicegui import events, ui, APIRouter, app

import globals
from ui.components.base import base_layout
from ui.components.notify import notify
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
def index():
    multiple = True
    M = globals.get_storage_manager()

    def update_grid(path: str):
        grid.options["rowData"] = [
            {
                "name": f"📁 <strong>{p.name}</strong>" if p.type == "dir" else p.name,
                "path": p.path,
                "size": bytes_to_human_readable(p.size) if p.size else "-",
                "raw_size": p.size if p.size else -1,
                "created_at": timestamp_to_human_readable(p.created_at) if p.created_at else "-",
                "updated_at": timestamp_to_human_readable(p.updated_at) if p.updated_at else "-",
            }
            for p in M.list_files(path)
        ]
        grid.update()

    def switch_lang():
        lang_code = app.storage.user.get("default_lang", "en_US")
        if lang_code == "en_US":
            lang_code = "zh_CN"
        else:
            lang_code = "en_US"
        app.storage.user["default_lang"] = lang_code
        ui.navigate.to(this_page_routes)

    ui.button("切换语言", on_click=switch_lang)

    with ui.card().classes("w-full h-screen"):
        grid = ui.aggrid(
            {
                "columnDefs": [
                    {"colId": "name", "field": "name", "headerName": _("File"), "type": "text"},
                    {"field": "size", "headerName": _("Size"), "type": "rightAligned", "maxWidth": 110},
                    {"field": "raw_size", "hide": True, "sortable": True},
                    {"field": "created_at", "headerName": _("Created At"), "type": "dateTimeString", "maxWidth": 170},
                    {"field": "updated_at", "headerName": _("Updated At"), "type": "dateTimeString", "maxWidth": 170},
                ],
                # "rowSelection": {"mode": "multiRow" if multiple else "singleRow"},
            },
            html_columns=[0],
            theme="material",
        ).classes("w-full h-full")

        update_grid("./")

    def handle_double_click(e: events.GenericEventArguments) -> None:
        print(e.args)
        try:
            path = Path(e.args["data"]["path"])
            update_grid(path.__str__())
        except Exception as e:
            notify.error(str(e))

    grid.on("cellDoubleClicked", handle_double_click)
