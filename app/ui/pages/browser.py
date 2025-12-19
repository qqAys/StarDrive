from fastapi.responses import RedirectResponse
from nicegui import APIRouter, app, ui

from app import globals
from app.core.i18n import _
from app.security.guards import require_user
from app.services.file_service import get_user_last_path
from app.ui.components.base import BaseLayout
from app.ui.components.table import FileBrowserTable

this_page_routes = "/home"


@app.get("/")
def index():
    return RedirectResponse(this_page_routes + "/")


@app.get(this_page_routes)
def browser_index():
    return RedirectResponse(this_page_routes + "/")


router = APIRouter(prefix=this_page_routes)


@router.page("/")
@require_user()
async def index():
    async with BaseLayout().render(header=True, footer=True, args={"title": _("Home")}):

        file_manager = globals.get_storage_manager()
        user_manager = globals.get_user_manager()

        current_user = await user_manager.current_user()

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
            file_manager=file_manager,
            current_user=current_user,
            target_path="" if user_last_path is None else f"./{user_last_path}",
            upload_component=upload_component,
            upload_dialog=upload_dialog,
            upload_dialog_close_button=dialog_close_button,
        )
        await file_browser_component.refresh()
