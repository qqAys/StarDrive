from fastapi.responses import RedirectResponse
from nicegui import APIRouter, app

import globals
from ui.components.base import base_layout
from ui.components.table import FileBrowserTable
from utils import _

this_page_routes = "/home"


@app.get("/")
def index():
    return RedirectResponse(this_page_routes + "/")


@app.get(this_page_routes)
def browser_index():
    return RedirectResponse(this_page_routes + "/")


router = APIRouter(prefix=this_page_routes)


@router.page("/")
# @router.page("/{path:path}")
@base_layout(header=True, footer=True, args={"title": _("Home")})
async def index(path: str = None):

    file_manager = globals.get_storage_manager()

    file_browser_component = FileBrowserTable(
        file_service=file_manager, target_path="" if path is None else f"./{path}"
    )
    await file_browser_component.refresh()
