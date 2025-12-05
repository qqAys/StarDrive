from pathlib import Path

from fastapi.responses import RedirectResponse
from nicegui import events, ui, APIRouter, app

import globals
from ui.components.header import Header
from ui.components.notify import notify
from utils import bytes_to_human_readable, _

this_page_routes = "/home"


@app.get("/")
def index():
    return RedirectResponse(this_page_routes)


router = APIRouter(prefix=this_page_routes)


@router.page("/")
def index():

    Header().render()

    multiple = True
    M = globals.get_storage_manager()

    def update_grid(path: str):
        grid.options["rowData"] = [
            {
                "name": f"📁 <strong>{p.name}</strong>" if p.type == "dir" else p.name,
                "path": p.path,
                "size": bytes_to_human_readable(p.size) if p.size else "-",
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
                    {"field": "name", "headerName": _("文件")},
                    {"field": "size", "headerName": _("大小")},
                ],
                "rowSelection": {"mode": "multiRow" if multiple else "singleRow"},
            },
            html_columns=[0],
        ).classes("w-full h-full")

        update_grid("./")

    def handle_double_click(e: events.GenericEventArguments) -> None:
        try:
            path = Path(e.args["data"]["path"])
            update_grid(path.__str__())
        except Exception as e:
            notify.error(str(e))

    grid.on("cellDoubleClicked", handle_double_click)
