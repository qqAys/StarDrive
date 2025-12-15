from fastapi.responses import RedirectResponse
from nicegui import APIRouter, app, ui

import globals
from services.file_service import get_user_last_path
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

    with ui.dialog().props("seamless position='bottom'") as upload_dialog:
        with ui.card().tight():
            dialog_close_button = (
                ui.button(icon="close")
                .props("dense square unelevated")
                .classes("w-full")
            )
            upload_component = (
                ui.upload(label=_("Upload files"), multiple=True, auto_upload=True)
                .props("hide-upload-btn no-thumbnails")
                .classes("max-w-full")
            )
            upload_component.set_visibility(True)

    user_last_path = get_user_last_path()

    file_browser_component = FileBrowserTable(
        file_service=file_manager,
        target_path="" if user_last_path is None else f"./{user_last_path}",
        upload_component=upload_component,
        upload_dialog=upload_dialog,
        upload_dialog_close_button=dialog_close_button,
    )
    await file_browser_component.refresh()
