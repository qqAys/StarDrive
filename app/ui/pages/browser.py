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
    """Redirect root path to the home page."""
    return RedirectResponse(f"{this_page_routes}/")


@app.get(this_page_routes)
def browser_index():
    """Redirect base home route to its index page."""
    return RedirectResponse(f"{this_page_routes}/")


router = APIRouter(prefix=this_page_routes)


@router.page("/")
@require_user
async def index():
    """
    Render the user's home file browser page.

    This page displays a file browser initialized at the user's last visited directory (if available),
    along with an upload dialog for adding new files.
    """
    async with BaseLayout().render(
        header=True,
        footer=True,
        args={"title": _("Home")},
    ) as (header, footer):
        file_manager = globals.get_storage_manager()
        current_user = header.get_user()

        # Upload dialog setup
        with ui.dialog().props("seamless position='bottom'") as upload_dialog:
            with ui.card().classes("w-full").tight():
                dialog_close_button = (
                    ui.button(icon="close")
                    .props("dense square unelevated")
                    .classes("w-full")
                )
                upload_component = (
                    ui.upload(
                        label=_("Upload files"),
                        multiple=True,
                        auto_upload=True,
                    )
                    .props("hide-upload-btn no-thumbnails")
                    .classes("w-full")
                )
                upload_component.set_visibility(True)

        # Determine initial path: use last visited path or root
        user_last_path = get_user_last_path()
        initial_path = "" if user_last_path is None else f"./{user_last_path}"

        footer_container = footer.inject()

        # Initialize and render the file browser
        file_browser_component = FileBrowserTable(
            file_manager=file_manager,
            current_user=current_user,
            target_path=initial_path,
            upload_component=upload_component,
            upload_dialog=upload_dialog,
            upload_dialog_close_button=dialog_close_button,
            footer_container=footer_container,
        )
        await file_browser_component.refresh()
