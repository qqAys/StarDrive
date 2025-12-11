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
@base_layout(header=True, footer=True, args={"title": _("Home")})
async def index():

    file_manager = globals.get_storage_manager()

    file_browser_component = FileBrowserTable(
        file_service=file_manager, initial_path="."
    )
    await file_browser_component.refresh()
