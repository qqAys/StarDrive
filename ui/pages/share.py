from datetime import datetime
from typing import Annotated

from fastapi import Depends
from nicegui import ui, app, APIRouter
from starlette.requests import Request
from starlette.responses import RedirectResponse

import globals
from api.download import verify_download_token
from models.file_download_model import FileDownloadInfo
from schemas.file_schema import FileMetadata, DirMetadata
from services.file_service import get_file_icon
from ui.components.base import BaseLayout
from ui.pages.error_page import render_404
from utils import _

this_page_routes = "/share"


@app.get("/")
def index():
    return RedirectResponse(this_page_routes + "/")


@app.get(this_page_routes)
def browser_index():
    return RedirectResponse(this_page_routes + "/")


router = APIRouter(prefix=this_page_routes)


@router.page("/{jwt_token}")
async def index(
    validated_data: Annotated[FileDownloadInfo, Depends(verify_download_token)],
    request: Request,
):
    if not validated_data:
        render_404(
            request.state.request_uuid,
            _("This shared link is no longer available"),
            _("It may have expired or the file was removed by the owner. 🧐"),
            back_button=False,
        )
        return

    with BaseLayout().render(header=True, footer=True, args={"title": _("Share")}):

        file_manager = globals.get_storage_manager()

        file_info: FileMetadata | DirMetadata = file_manager.get_file_metadata(
            validated_data.path
        )

        # ---------- helpers ----------

        def _fmt_ts(ts: float | None) -> str:
            if not ts:
                return "-"
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")

        def _kv(label: str, value_el: ui.element):
            with ui.row(wrap=False).classes(
                "w-full justify-between items-center text-sm"
            ):
                ui.label(label).classes("text-gray-500")
                value_el

        # ---------- async action ----------

        async def calculate_dir_size():
            size_label.text = _("Calculating...")
            calc_btn.disable()

            try:
                dir_size = await file_manager.get_directory_size(file_info.path)
                size_label.text = f"{dir_size} bytes"
            finally:
                calc_btn.enable()

        # ---------- UI ----------

        icon = get_file_icon(file_info.type, file_info.extension)

        with ui.card().classes("w-full max-w-3xl mx-auto p-6 gap-4"):

            # ===== Header =====
            with ui.row().classes("items-center gap-3"):
                ui.icon(icon).classes("text-4xl text-primary")
                with ui.column().classes("gap-1"):
                    ui.label(file_info.name).classes("text-xl font-bold break-all")

            ui.separator()

            # ===== Base Info =====
            with ui.column().classes("gap-2"):

                _kv(_("Type"), ui.label(_(file_info.type.value)))

                # ---- Size row (with calc button) ----
                with ui.row().classes("w-full justify-between items-center text-sm"):
                    ui.label(_("Size")).classes("text-gray-500")

                    with ui.row().classes("items-center gap-2"):
                        size_label = ui.label(
                            f"{file_info.size} bytes" if not file_info.is_dir else "-"
                        ).classes("font-medium")

                        calc_btn = (
                            ui.button(
                                icon="calculate",
                                color="green",
                                on_click=calculate_dir_size,
                            )
                            .props("flat dense")
                            .tooltip(_("Calculate directory size"))
                        )

                        if not file_info.is_dir or file_info.num_children == 0:
                            calc_btn.disable()
                            if file_info.is_dir:
                                size_label.text = _("Directory is empty")

                _kv(
                    _("Extension"),
                    ui.label(file_info.extension or "-").classes("font-medium"),
                )

            ui.separator()

            # ===== Time Info =====
            with ui.column().classes("gap-2"):
                _kv(_("Created at"), ui.label(_fmt_ts(file_info.created_at)))
                _kv(_("Modified at"), ui.label(_fmt_ts(file_info.modified_at)))
                _kv(_("Accessed at"), ui.label(_fmt_ts(file_info.accessed_at)))
                _kv(
                    _("Status changed at"),
                    ui.label(_fmt_ts(file_info.status_changed_at)),
                )

            # ===== Dir only =====
            if isinstance(file_info, DirMetadata):
                ui.separator()
                with ui.column().classes("gap-2"):
                    _kv(
                        _("Children"),
                        ui.label(str(file_info.num_children)).classes("font-medium"),
                    )

            # ===== Actions =====
            ui.separator()
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button(_("Download"), icon="download")
