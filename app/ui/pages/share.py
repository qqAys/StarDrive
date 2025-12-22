from datetime import datetime
from pathlib import Path
from typing import Annotated, Callable

from fastapi import Depends
from nicegui import ui, app, APIRouter
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app import globals
from app.core.i18n import _
from app.models.file_download_model import FileDownloadInfo
from app.schemas.file_schema import FileMetadata, DirMetadata, FileSource
from app.services.download_service import verify_download_token
from app.services.file_service import get_file_icon, generate_download_url
from app.ui.components.base import BaseLayout
from app.ui.components.dialog import ConfirmDialog, FileBrowserDialog
from app.ui.pages.error_page import render_404
from app.utils.size import bytes_to_human_readable

this_page_routes = "/share"


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

    async with BaseLayout().render(
        header=True, footer=True, args={"title": _("Share")}
    ):

        file_manager = globals.get_storage_manager()

        file_info: FileMetadata | DirMetadata = file_manager.get_file_metadata(
            validated_data.path
        )

        file_path = Path(file_info.path)

        # ---------- helpers ----------

        def _fmt_ts(ts: float | None) -> str:
            if not ts:
                return "-"
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")

        def _kv(label: str, value: str | Callable[[], ui.element]):
            with ui.row(wrap=False).classes(
                "w-full justify-between items-center text-sm"
            ):
                ui.label(label).classes("text-gray-500")
                if callable(value):
                    value()
                else:
                    ui.label(value).classes("font-medium")

        # ---------- async action ----------

        async def calculate_dir_size():
            size_label.text = _("Calculating...")
            calc_btn.disable()

            try:
                dir_size = await file_manager.get_directory_size(file_info.path)
                size_label.text = bytes_to_human_readable(dir_size)
            finally:
                calc_btn.enable()

        async def on_explorer_button_click():
            r = await FileBrowserDialog(file_manager, file_path).open()

        async def on_download_button_click():
            if file_info.is_dir:
                confirm = await ConfirmDialog(
                    _("Confirm Download"),
                    _(
                        "You selected a folder. It will be compressed into a **single tar.gz file** for download. "
                    )
                    + _("Are you sure you want to download **`{}`**? ").format(
                        file_info.name
                    ),
                ).open()
            else:
                confirm = await ConfirmDialog(
                    _("Confirm Download"),
                    _("Are you sure you want to download **`{}`**? ").format(
                        file_info.name
                    ),
                ).open()

            if confirm:
                download_url = await generate_download_url(
                    target_path=file_info.path,
                    name=file_info.name,
                    type_=file_info.type,
                    source=FileSource.DOWNLOAD,
                    share_id=validated_data.id,
                )
                if not download_url:
                    return
                ui.navigate.to(download_url)
                return
            else:
                return

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
            with ui.column().classes("w-full justify-between gap-2"):

                _kv(_("Type"), _(file_info.type.value))

                # ---- Size row (with calc button) ----
                with ui.row().classes("w-full justify-between items-center text-sm"):
                    ui.label(_("Size")).classes("text-gray-500")

                    with ui.row().classes("items-center gap-2"):
                        size = bytes_to_human_readable(
                            file_info.size if file_info.size else 0
                        )
                        size_label = ui.label(size).classes("font-medium")

                        if isinstance(file_info, DirMetadata):
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
                    file_info.extension or "-",
                )

            ui.separator()

            # ===== Time Info =====
            with ui.column().classes("w-full justify-between gap-2"):
                _kv(_("Created at"), _fmt_ts(file_info.created_at))
                _kv(_("Modified at"), _fmt_ts(file_info.modified_at))
                _kv(_("Accessed at"), _fmt_ts(file_info.accessed_at))
                _kv(
                    _("Status changed at"),
                    _fmt_ts(file_info.status_changed_at),
                )

            # ===== Dir only =====
            if isinstance(file_info, DirMetadata):
                ui.separator()
                with ui.column().classes("w-full justify-between gap-2"):
                    _kv(
                        _("Children"),
                        str(file_info.num_children),
                    )

            # ===== Actions =====
            ui.separator()
            with ui.row().classes("w-full justify-end gap-2"):
                if file_info.is_dir:
                    ui.button(
                        _("Explore"), icon="explorer", on_click=on_explorer_button_click
                    )
                ui.button(
                    _("Download"), icon="download", on_click=on_download_button_click
                )
