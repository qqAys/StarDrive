from pathlib import Path

from nicegui import events, ui, APIRouter

import globals
from utils import bytes_to_human_readable, _

router = APIRouter(prefix="/home")


@router.page("/")
def index():
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
        path = Path(e.args["data"]["path"])
        update_grid(path.__str__())

    grid.on("cellDoubleClicked", handle_double_click)
