from nicegui import ui

from app.config import settings
from app.core.i18n import _
from app.models.file_download_model import FileDownloadInfo
from app.schemas.file_schema import FileType
from app.ui.components.base import BaseLayout
from app.ui.components.notify import notify


async def render_share_access_page(
    share_info: FileDownloadInfo, share_by_name: str = None
):
    item_type = _("directory") if share_info.type == FileType.DIR else _("file")
    async with BaseLayout().render(
        header=False, footer=True, args={"from_login_page": True}
    ):
        with ui.card(align_items="center").classes("absolute-center w-max"):
            with ui.card_section().classes("w-full"):
                # Header
                with ui.column().classes("mb-4"):
                    with ui.row().classes("text-3xl items-center gap-2"):
                        ui.image("/android-chrome-512x512.png").classes("w-8 h-8")
                        ui.label(settings.APP_NAME).classes("text-2xl font-bold")
                    ui.label(
                        _("Enter the access code to access this {}").format(item_type)
                    ).classes("text-xs text-gray-500")

                with ui.card().classes("w-full mb-4"):
                    ui.label(_("Share Information")).classes("text-sm font-bold mb-2")
                    ui.label(_("Name: {}").format(share_info.name)).classes("text-xs")
                    if share_info.user_id:
                        ui.label(_("Shared By User: {}").format(share_by_name)).classes(
                            "text-xs"
                        )
                    ui.label(
                        _("Expires At: {}").format(
                            share_info.expires_at_utc.strftime("%Y-%m-%d %H:%M:%S %Z")
                        )
                    ).classes("text-xs")

                # Access code input
                access_code_input = (
                    ui.input(
                        _("Access Code"),
                        placeholder=_("Enter your access code here"),
                    )
                    .classes("w-full")
                    .props("autofocus")
                )

                # 验证逻辑
                async def verify_access_code():
                    code_entered = access_code_input.value.strip()
                    if not code_entered:
                        notify.warning(_("Please enter the access code"))
                        return

                    if code_entered == share_info.access_code:
                        notify.success(_("Access granted"))
                        # 这里可以做进一步操作，比如跳转下载页
                        # ui.navigate.to(f"/download/{share_info.id}")
                    else:
                        notify.error(_("Invalid access code"))
                        access_code_input.value = ""  # 清空输入

                # 绑定回车和按钮
                access_code_input.on("keyup.enter", verify_access_code)

                ui.button(
                    _("Submit"), on_click=verify_access_code, icon="check"
                ).classes("w-full mt-4")
