import asyncio
import csv
import hashlib
import html
import io
import json
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone, date, time
from enum import Enum
from pathlib import Path
from typing import Optional, Callable

from nicegui import ui, events
from nicegui.events import KeyEventArguments

from app.api.preview import (
    create_preview_file_url,
    create_storage_preview_url,
    find_libreoffice_command,
)
from app.core.paths import PREVIEW_CACHE_DIR
from app.core.i18n import _
from app.models.user_model import User
from app.schemas.file_schema import (
    FILE_NAME_FORBIDDEN_CHARS,
    FileMetadata,
    DirMetadata,
    FileSource,
    FileType,
)
from app.security.access_code import generate_access_code
from app.services.file_service import (
    get_user_share_links,
    delete_download_link,
    StorageManager,
    get_file_icon,
    generate_download_url,
    get_image_info,
)
from app.services.user_service import get_user_timezone
from app.ui.components.button import custom_button
from app.ui.components.clipboard import copy_to_clipboard
from app.ui.components.notify import notify
from app.ui.components.label import label
from app.ui.theme import theme
from app.utils.size import bytes_to_human_readable
from app.utils.time import timestamp_to_human_readable, utc_now


class Dialog:
    dialog_props = 'backdrop-filter="blur(2px) brightness(90%)"'
    title_class = "text-lg font-bold break-words max-w-full"

    def __init__(self):
        self.dialog = ui.dialog().props(self.dialog_props)

    async def open(self):
        return await self.dialog


class SearchDialog(Dialog):
    PAGE_SIZE = 30

    def __init__(self, file_service: StorageManager, current_path: Path):
        super().__init__()
        self.search_input: Optional[ui.input] = None
        self.file_manager = file_service
        self.current_path = current_path
        self.last_query: Optional[str] = None
        self.results_list: Optional[ui.list] = None
        self.offset = 0
        self.loading = False
        self.has_more = True
        self.search_task: Optional[asyncio.Task] = None

    async def open(self) -> Optional[FileMetadata | DirMetadata | None]:
        with self.dialog, ui.card().tight().classes("w-full h-[600px]"):
            with ui.row().classes("w-full items-center px-4"):
                self.search_input = (
                    ui.input(
                        label=_("Search in {folder}").format(
                            folder=self.current_path.name or "."
                        ),
                        on_change=self.on_input_change,
                    )
                    .classes("flex-grow")
                    .props("autofocus")
                )
                with self.search_input.add_slot("append"):
                    ui.icon("search")
            with ui.scroll_area(on_scroll=self.on_scroll).classes("w-full h-full"):
                self.results_list = (
                    ui.list()
                    .classes("w-full h-full overflow-auto")
                    .props("bordered separator")
                )
        return await self.dialog

    async def on_input_change(self):
        await asyncio.sleep(0.6)
        query = self.search_input.value.strip()
        if query == self.last_query:
            return
        self.last_query = query
        self.offset = 0
        self.has_more = True
        self.results_list.clear()
        if self.search_task:
            self.search_task.cancel()
        if not query:
            return
        self.search_task = asyncio.create_task(self.load_more())

    async def load_more(self):
        if self.loading or not self.has_more:
            return
        self.loading = True
        results = await self.file_manager.search(
            query=self.last_query,
            remote_path=str(self.current_path),
            offset=self.offset,
            limit=self.PAGE_SIZE,
        )
        if not results:
            self.has_more = False
            self.loading = False
            self.render_no_more_results()
            return
        with self.results_list:
            for item in results:
                with ui.item(
                    on_click=lambda item_=item: self.dialog.submit(item_)
                ).props("clickable"):
                    with ui.item_section().classes(
                        "w-full break-all whitespace-normal"
                    ):
                        ui.html(
                            f"{get_file_icon(item.type, item.extension)} <b>{item.name}</b>",
                            sanitize=False,
                        )
                        ui.markdown(f"`{item.path}`").classes("text-xs")
        self.offset += len(results)
        if len(results) < self.PAGE_SIZE:
            self.has_more = False
            self.render_no_more_results()
        self.loading = False

    def render_no_more_results(self):
        with self.results_list:
            with ui.item().props("disabled"):
                with ui.column().classes("w-full items-center gap-1"):
                    custom_button(
                        text=_("No more results"), icon="search_off", disabled=True
                    )
                    ui.markdown(_("Try searching in a different folder.")).classes(
                        "text-xs my-0 py-0"
                    )
                    ui.markdown(
                        _("Current folder: **{path}**").format(path=self.current_path)
                    ).classes("text-xs my-0 py-0")

    async def on_scroll(self, e: events.ScrollEventArguments):
        if e.vertical_percentage == 1:
            await self.load_more()


class InputDialog(Dialog):
    def __init__(
        self,
        title: str,
        input_label: str,
        input_value: str = "",
        message: str | None = None,
    ):
        super().__init__()
        self.title = title
        self.message = message
        self.input_label = input_label
        self.input_value = input_value
        self.dialog = ui.dialog().props(self.dialog_props)

    async def open(self) -> str | None:
        with self.dialog, ui.card().classes("w-full"):
            ui.label(self.title).classes(self.title_class)
            if self.message:
                ui.markdown(self.message).classes("break-words max-w-full")
            input_component = ui.input(
                label=self.input_label, value=self.input_value
            ).classes("w-full")
            with ui.row().classes("w-full justify-between"):
                ui.button(
                    _("Confirm"),
                    on_click=lambda: self.dialog.submit(input_component.value.strip()),
                    color=theme().positive,
                )
                ui.button(
                    _("Cancel"),
                    on_click=lambda: self.dialog.submit(None),
                )
        return await self.dialog


class ConfirmDialog(Dialog):
    def __init__(
        self, title: str, message: str | list | None = None, warning: bool = False
    ):
        super().__init__()
        self.title = title
        self.message = message
        self.warning = warning
        self.dialog = ui.dialog().props(self.dialog_props)

    async def open(self) -> bool:
        with self.dialog, ui.card():
            ui.label(self.title).classes(self.title_class)
            if self.message:
                if isinstance(self.message, str):
                    ui.markdown(self.message).classes("break-words max-w-full")
                elif isinstance(self.message, list):
                    formatted = "\n".join(f"- `{msg}`" for msg in self.message)
                    ui.markdown(formatted).classes("break-words max-w-full")
            with ui.row().classes("w-full justify-between"):
                ui.button(
                    _("Confirm"),
                    on_click=lambda: self.dialog.submit(True),
                    color="negative" if self.warning else "positive",
                ).props("autofocus")
                ui.button(
                    _("Cancel"),
                    on_click=lambda: self.dialog.submit(False),
                )
        return await self.dialog


class RenameDialog(InputDialog):
    def __init__(self, current_name: str, old_name: str):
        super().__init__(
            title=_("Rename {name}").format(name=current_name),
            input_label=_("New name"),
            input_value=old_name,
        )
        self.old_name = old_name

    async def open(self) -> str | None:
        with self.dialog, ui.card().classes("w-full"):
            ui.label(self.title).classes(self.title_class)
            ui.input(label=_("Current name"), value=self.old_name).classes(
                "w-full"
            ).disable()
            input_component = (
                ui.input(label=self.input_label, value=self.input_value)
                .classes("w-full")
                .props("autofocus")
            )

            async def on_confirm():
                new_val = input_component.value.strip()
                if not new_val:
                    notify.warning(_("New name cannot be empty"))
                    return
                if new_val == self.old_name:
                    notify.warning(_("New name cannot be the same as the current name"))
                    return
                if any(char in new_val for char in FILE_NAME_FORBIDDEN_CHARS):
                    notify.warning(
                        _("File name cannot contain: {chars}").format(
                            chars=", ".join(FILE_NAME_FORBIDDEN_CHARS)
                        )
                    )
                    return
                if new_val.endswith("."):
                    notify.warning(_("File name cannot end with a dot"))
                    return
                confirm = await ConfirmDialog(
                    title=_("Confirm Rename"),
                    message=_(
                        "Are you sure you want to rename **{old}** to **{new}**?"
                    ).format(old=self.old_name, new=new_val),
                ).open()
                if confirm:
                    self.dialog.submit(new_val)

            with ui.row().classes("w-full justify-between"):
                ui.button(_("Confirm"), on_click=on_confirm, color="green")
                ui.button(_("Cancel"), on_click=lambda: self.dialog.submit(None))
        return await self.dialog


class ShareDialog(Dialog):
    def __init__(self, file_name: str, current_user: User):
        super().__init__()
        self.title = _("Share {file}").format(file=file_name)
        self.file_name = file_name
        self.current_user = current_user
        self.dialog = ui.dialog().props(self.dialog_props)

    async def open(self) -> dict | None:
        with self.dialog, ui.card().classes("w-full"):
            ui.label(self.title).classes(self.title_class)

            # Load existing share links
            user_share_links = await get_user_share_links(
                self.current_user, self.file_name
            )
            share_links = {link.id: link for link in user_share_links}
            links_section = ui.column().classes("w-full")
            links_section.set_visibility(bool(share_links))

            with links_section:
                ui.separator()
                count_label = ui.label().classes("text-base font-bold")

                def update_count_and_visibility():
                    count = len(share_links)
                    count_label.text = _("{count} sharing links").format(count=count)
                    links_section.set_visibility(count > 0)

                update_count_and_visibility()

                all_share_link_cards: dict[str, ui.card] = {}

                async def delete_share_link(download_id: str) -> bool:
                    confirm = await ConfirmDialog(
                        title=_("Confirm Delete"),
                        message=_("Are you sure you want to delete this share link?"),
                        warning=True,
                    ).open()
                    if not confirm:
                        return False
                    try:
                        await delete_download_link(download_id)
                        card = all_share_link_cards.pop(download_id, None)
                        if card:
                            card.remove(card)
                        share_links.pop(download_id, None)
                        update_count_and_visibility()
                        notify.success(_("Share link deleted"))
                        return True
                    except Exception as e:
                        notify.error(
                            _("Failed to delete share link: {error}").format(
                                error=str(e)
                            )
                        )
                        return False

                # List share links
                with ui.scroll_area().classes("w-full"):
                    for link in user_share_links:
                        link_url = link.url
                        expire_local = link.expires_at_utc.astimezone(
                            get_user_timezone()
                        ).strftime("%Y-%m-%d %H:%M:%S %Z")
                        with ui.card().classes("w-full") as share_card:
                            ui.input(label=_("Share link"), value=link_url).props(
                                "readonly dense"
                            ).classes("w-full")
                            with ui.row().classes("w-full items-center gap-3"):
                                if link.access_code:
                                    ui.label(link.access_code).classes(
                                        "text-sm font-semibold px-3 py-1 rounded bg-blue-100 text-blue-700 select-all"
                                    )
                                else:
                                    ui.label(_("Public Access")).classes(
                                        "text-xs font-semibold text-green-700 bg-green-100 rounded-full px-3 py-1"
                                    )
                                ui.label(
                                    _("Expired")
                                    if utc_now() > link.expires_at_utc
                                    else _("Valid")
                                ).classes(
                                    "text-xs text-white font-semibold bg-red-500 rounded-full px-2 py-0.5"
                                    if utc_now() > link.expires_at_utc
                                    else "text-xs text-white font-semibold bg-green-500 rounded-full px-2 py-0.5"
                                )
                                ui.label(
                                    _("Expires at {time}").format(time=expire_local)
                                ).classes("text-xs text-gray-500")
                            with ui.row().classes("w-full justify-end gap-2"):
                                ui.button(
                                    _("Copy"),
                                    icon="content_copy",
                                    on_click=lambda url=link_url: copy_to_clipboard(
                                        url, _("Share link copied to clipboard.")
                                    ),
                                ).props("flat dense")
                                ui.button(
                                    _("Open"),
                                    icon="open_in_new",
                                    on_click=lambda url=link_url: ui.navigate.to(
                                        url, new_tab=True
                                    ),
                                ).props("flat dense")
                                ui.button(
                                    _("Delete"),
                                    icon="delete",
                                    color="red",
                                    on_click=lambda d_id=link.id: delete_share_link(
                                        d_id
                                    ),
                                ).props("flat dense")
                            all_share_link_cards[link.id] = share_card

            # Create new share link
            ui.separator()
            ui.label(_("Create new sharing link")).classes("text-base font-bold")
            user_tz = get_user_timezone()
            now_local = datetime.now(user_tz)
            expire_type = ui.toggle(
                [_("Expire after"), _("Expire after days")], value=_("Expire after")
            )

            with ui.row().classes("w-full justify-between") as datetime_picker:
                date_input = ui.date_input(
                    _("Expire date"), value=now_local.strftime("%Y-%m-%d")
                ).classes("md:w-auto w-full")
                date_input.picker.props[":options"] = (
                    f'date => date >= "{now_local.strftime("%Y/%m/%d")}"'
                )
                time_input = ui.time_input(_("Expire time"), value="00:00").classes(
                    "md:w-auto w-full"
                )
                datetime_picker.set_visibility(True)

            with ui.row().classes("w-full justify-between") as days_picker:
                days = ui.number(
                    _("Expire days"),
                    value=1,
                    min=1,
                    max=365,
                    precision=0,
                    format="%.0f",
                ).classes("w-full")
                days_picker.set_visibility(False)

            expire_type.on_value_change(
                lambda e: (
                    days_picker.set_visibility(e.value == _("Expire after days")),
                    datetime_picker.set_visibility(e.value == _("Expire after")),
                )
            )

            ui.label(_("Access code")).classes("text-base font-bold")
            with ui.row(wrap=False).classes("w-full justify-between"):
                access_enabled = ui.checkbox(_("Generate"), value=False)
                access_input = (
                    ui.input(
                        label=_("Access code"),
                        placeholder=_("Will be generated automatically"),
                    )
                    .props("readonly dense")
                    .classes("w-full")
                )
                with access_input.add_slot("append"):
                    regen_btn = ui.button(_("Regenerate"), icon="refresh").props(
                        "flat dense"
                    )
                    ui.button(
                        _("Copy"),
                        icon="content_copy",
                        on_click=lambda: copy_to_clipboard(
                            access_code, _("Access code copied.")
                        ),
                    ).props("flat dense")
                access_input.set_visibility(False)
                regen_btn.set_visibility(False)
                access_code: str | None = None

                def update_access_ui(enabled: bool):
                    nonlocal access_code
                    access_input.set_visibility(enabled)
                    regen_btn.set_visibility(enabled)
                    if enabled:
                        access_code = generate_access_code()
                        access_input.value = access_code
                    else:
                        access_code = None
                        access_input.value = ""

                def regen_access_code():
                    nonlocal access_code
                    access_code = generate_access_code()
                    access_input.value = access_code

                access_enabled.on_value_change(lambda e: update_access_ui(e.value))
                regen_btn.on_click(regen_access_code)

            def on_confirm():
                if len(all_share_link_cards) >= 10:
                    notify.error(
                        _(
                            "Maximum number of share links reached. Delete some before creating a new one."
                        )
                    )
                    return
                if expire_type.value == _("Expire after"):
                    if not date_input.value or not time_input.value:
                        notify.warning(_("Please select a valid expire time"))
                        return
                    selected_dt = (
                        datetime.combine(
                            date.fromisoformat(date_input.value),
                            time(*map(int, time_input.value.split(":"))),
                        )
                        .replace(tzinfo=user_tz)
                        .astimezone(timezone.utc)
                    )
                    if selected_dt < utc_now():
                        notify.warning(_("Expire date cannot be before now"))
                        return
                    self.dialog.submit(
                        {
                            "expire_datetime_utc": selected_dt,
                            "expire_days": None,
                            "access_code": access_code,
                        }
                    )
                else:
                    self.dialog.submit(
                        {
                            "expire_datetime_utc": None,
                            "expire_days": int(days.value),
                            "access_code": access_code,
                        }
                    )

            with ui.row().classes("w-full justify-between"):
                ui.button(_("Confirm"), on_click=on_confirm, color="green")
                ui.button(_("Cancel"), on_click=lambda: self.dialog.submit(None))
        return await self.dialog


class FileBrowserDialog(Dialog):
    """File browser dialog for viewing shared folder contents."""

    def __init__(self, file_service: StorageManager, target_path: Path, share_id: str):
        super().__init__()
        self.file_manager = file_service
        self.target_path = target_path
        self.share_id = share_id
        self.dialog = ui.dialog().props(self.dialog_props)
        self.title_label: Optional[ui.label] = None

    async def open(self):
        with self.dialog, ui.card().classes("w-full"):
            # Header
            with ui.row().classes("w-full justify-between"):
                self.title_label = ui.label().classes(self.title_class)
                ui.button(
                    icon="close", on_click=lambda: self.dialog.submit(None)
                ).props("flat dense")

            with ui.scroll_area().classes("w-full h-[600px]"):
                columns = [
                    {"name": "name", "label": _("Name"), "field": "name"},
                    {
                        "name": "size",
                        "label": _("Size"),
                        "field": "size",
                        "align": "right",
                        "style": "width:0px",
                    },
                ]
                table = ui.table(
                    columns=columns,
                    rows=[],
                    column_defaults={
                        "sortable": False,
                        "align": "left",
                        "required": True,
                    },
                ).classes("w-full")
                target_path = self.target_root_path

                # Back to parent button
                with table.add_slot("top-left"):
                    with ui.row().classes("items-center gap-x-2"):
                        ui.button(
                            icon="arrow_upward",
                            on_click=lambda: refresh_table(target_path.parent),
                        ).props("flat dense").tooltip(_("Back to parent directory"))

                # No data message
                with table.add_slot("no-data"):
                    with ui.row().classes("items-center"):
                        ui.icon("warning").classes("text-2xl")
                        ui.label(_("No files or directories found.")).classes(
                            "font-bold"
                        )

                def refresh_table(path: Path):
                    nonlocal target_path
                    # Prevent navigating above root
                    if (
                        path != self.target_root_path
                        and self.target_root_path not in path.parents
                    ):
                        notify.warning(
                            _(
                                "Already at the share root directory. Cannot go back further."
                            )
                        )
                        return
                    target_path = path
                    display_path = (
                        "."
                        if target_path == self.target_root_path
                        else target_path.relative_to(self.target_root_path)
                    )
                    self.title_label.text = _("Browsing {path}").format(
                        path=display_path
                    )
                    rows = []
                    for meta in self.file_manager.list_files(str(path)):
                        rows.append(
                            {
                                "name": f"{get_file_icon(meta.type, meta.extension)} {meta.name}",
                                "raw_name": meta.name,
                                "size": bytes_to_human_readable(meta.size),
                                "path": meta.path,
                                "is_dir": meta.is_dir,
                            }
                        )
                    table.rows = rows

                async def handle_row_double_click(e: events.GenericEventArguments):
                    click_event_params, click_row, click_index = e.args
                    click_path = click_row["path"]
                    file_name = click_row["raw_name"]
                    if click_row["is_dir"]:
                        refresh_table(target_path / file_name)
                    else:
                        confirm = await ConfirmDialog(
                            _("Confirm Download"),
                            _("Are you sure you want to download **`{name}`**?").format(
                                name=file_name
                            ),
                        ).open()
                        if confirm:
                            download_url = await generate_download_url(
                                target_path=click_path,
                                name=file_name,
                                type_=FileType.FILE,
                                source=FileSource.DOWNLOAD,
                                share_id=self.share_id,
                                base_path=str(self.target_path),
                            )
                            if download_url:
                                ui.navigate.to(download_url)

                table.on("row-dblclick", handle_row_double_click)
                refresh_table(target_path)
        return await self.dialog


class MoveDialog(Dialog):
    """Move dialog that returns the selected target folder path."""

    def __init__(self, file_service: StorageManager, files: list, current_path: Path):
        super().__init__()
        self.title_label: Optional[ui.label] = None
        self.file_manager = file_service
        self.files = files
        self.current_path = current_path
        self.dialog = ui.dialog().props(self.dialog_props)

    async def open(self):
        with self.dialog, ui.card().classes("w-full"):
            self.title_label = ui.label().classes(self.title_class)
            columns = [{"name": "name", "label": _("Directory"), "field": "name"}]
            dir_table = ui.table(
                columns=columns,
                rows=[],
                column_defaults={"sortable": True, "align": "left", "required": True},
            ).classes("w-full")
            target_path = self.current_path

            # Back to parent slot
            with dir_table.add_slot("top-left"):
                with ui.row().classes("items-center gap-x-0"):
                    ui.button(
                        icon="arrow_upward",
                        on_click=lambda: refresh_dir_table(target_path, True),
                    ).props("flat dense").tooltip(_("Back to parent directory"))

            # No data message
            with dir_table.add_slot("no-data"):
                with ui.row().classes("items-center"):
                    ui.icon("warning").classes("text-2xl")
                    ui.label(_("No directories found.")).classes("font-bold")

            def refresh_dir_table(path: Path, parent: bool = False):
                nonlocal target_path
                if parent:
                    path = path.parent
                self.title_label.text = _("Move {items} to {path}").format(
                    items=(
                        f"{len(self.files)} items"
                        if len(self.files) > 1
                        else self.files[0]
                    ),
                    path=str(path),
                )
                rows = []
                for meta_data in self.file_manager.list_files(str(path)):
                    if meta_data.is_dir:
                        rows.append(
                            {
                                "name": f"{get_file_icon(meta_data.type, meta_data.extension)} {meta_data.name}",
                                "path": meta_data.path,
                            }
                        )
                dir_table.rows = rows
                target_path = path

            refresh_dir_table(target_path)

            async def handle_row_double_click(e: events.GenericEventArguments):
                click_event_params, click_row, click_index = e.args
                refresh_dir_table(Path(click_row["path"]))

            dir_table.on("row-dblclick", handle_row_double_click)

            with ui.row().classes("w-full justify-between"):
                ui.button(
                    _("Confirm"),
                    on_click=lambda: self.dialog.submit(target_path),
                    color="green",
                )
                ui.button(_("Cancel"), on_click=lambda: self.dialog.submit(None))
        return await self.dialog


class MetadataDialog(Dialog):
    def __init__(
        self,
        current_user: User,
        file_manager: StorageManager,
        metadata: FileMetadata | DirMetadata,
        current_path: Path,
        refresh_browser_func: Callable,
    ):
        super().__init__()
        self.current_path = current_path
        self.metadata = metadata
        self.is_dir = self.metadata.is_dir
        self.file_manager = file_manager
        self.current_user = current_user
        self.refresh_browser = refresh_browser_func
        self.size_label: ui.label | None = None
        self.calc_btn: ui.button | None = None
        self.user_timezone = get_user_timezone()
        self.dialog = ui.dialog().props(self.dialog_props)

    async def open(self):
        with self.dialog, ui.card().classes("w-full"):
            with ui.row().classes("w-full justify-between"):
                ui.label(_("Metadata")).classes(self.title_class)
                ui.button(
                    icon="close", on_click=lambda: self.dialog.submit(None)
                ).props("flat dense")

            with ui.card().props("bordered flat").classes("w-full"):
                with ui.list().props("dense separator").classes("w-full"):
                    info = {
                        _("Name"): self.metadata.name,
                        _("Path"): self.metadata.path,
                        _("Type"): self.metadata.type,
                        _("Size"): bytes_to_human_readable(self.metadata.size),
                        **(
                            {_("Direct children"): self.metadata.num_children}
                            if self.is_dir
                            else {}
                        ),
                        _("Extension"): self.metadata.extension or "-",
                        _("Accessed"): timestamp_to_human_readable(
                            self.metadata.accessed_at, self.user_timezone
                        ),
                        _("Created"): timestamp_to_human_readable(
                            self.metadata.created_at, self.user_timezone
                        ),
                        _("Modified"): timestamp_to_human_readable(
                            self.metadata.modified_at, self.user_timezone
                        ),
                        _("Status Changed"): timestamp_to_human_readable(
                            self.metadata.status_changed_at, self.user_timezone
                        ),
                    }
                    for k, v in info.items():
                        with ui.item():
                            with ui.row(wrap=False).classes("w-full items-center"):
                                ui.label(k).classes("font-bold w-2/7")
                                if k == _("Size") and self.metadata.is_dir:
                                    self.size_label = ui.label(
                                        _("Click to calculate")
                                    ).classes("w-5/7")
                                    self.calc_btn = (
                                        ui.button(
                                            icon="calculate",
                                            color="green",
                                            on_click=self.calculate_dir_size,
                                        )
                                        .props("flat dense no-caps")
                                        .classes(
                                            "absolute right-0 top-1/2 -translate-y-1/2"
                                        )
                                        .tooltip(_("Calculate directory size"))
                                    )
                                    if self.metadata.num_children == 0:
                                        self.calc_btn.disable()
                                        self.size_label.text = _("Directory is empty")
                                else:
                                    ui.label(v).classes("w-5/7 text-pretty break-words")

            with ui.grid(columns=3).classes("w-full justify-between"):
                ui.button(
                    _("Delete"),
                    icon="delete_forever",
                    on_click=self.on_delete_button_click,
                    color="red",
                )
                ui.button(
                    _("Move"),
                    icon="drive_file_move",
                    on_click=self.on_move_button_click,
                    color="amber",
                )
                ui.button(
                    _("Rename"),
                    icon="drive_file_rename_outline",
                    on_click=self.on_rename_button_click,
                    color="gray-400",
                )

            with ui.grid(columns=2).classes("w-full justify-between"):
                ui.button(
                    _("Share"),
                    icon="share",
                    on_click=self.on_share_button_click,
                    color="cyan",
                )
                ui.button(
                    _("Download"),
                    icon="download",
                    on_click=self.on_download_button_click,
                    color="blue",
                )

        return await self.dialog

    async def calculate_dir_size(self):
        self.size_label.text = _("Calculating...")
        dir_size = await self.file_manager.get_directory_size(self.metadata.path)
        self.size_label.text = bytes_to_human_readable(dir_size)

    async def on_delete_button_click(self):
        confirm = await ConfirmDialog(
            _("Confirm Delete"),
            _("Are you sure you want to delete **`{name}`**").format(
                name=self.metadata.name
            ),
            warning=True,
        ).open()
        if confirm:
            try:
                self.file_manager.delete_file(self.metadata.path)
                notify.success(_("Deleted successfully"))
            except Exception as e:
                notify.error(str(e))
            await self.refresh_browser()

    async def on_rename_button_click(self):
        new_name = await RenameDialog(
            current_name=self.metadata.name, old_name=self.metadata.name
        ).open()
        if new_name:
            new_path = Path(self.metadata.path).parent / new_name
            if self.file_manager.exists(new_path):
                notify.warning(_("A file or folder with this name already exists."))
                return
            try:
                self.file_manager.move_file(self.metadata.path, new_path)
                notify.success(_("Renamed successfully"))
            except Exception as e:
                notify.error(str(e))
            await self.refresh_browser()

    async def on_move_button_click(self):
        target_path = await MoveDialog(
            self.file_manager, [self.metadata.name], self.current_path
        ).open()
        if target_path:
            if target_path == self.current_path:
                notify.error(_("Cannot move to the same folder."))
                return
            try:
                self.file_manager.move_file(
                    self.metadata.path, target_path / self.metadata.name
                )
                notify.success(
                    _("Moved successfully to {path}").format(
                        path=target_path / self.metadata.name
                    )
                )
            except Exception as e:
                notify.error(str(e))
            await self.refresh_browser()

    async def on_share_button_click(self):
        expire_define = await ShareDialog(
            file_name=self.metadata.name, current_user=self.current_user
        ).open()
        if expire_define:
            download_url = await generate_download_url(
                current_user=self.current_user,
                target_path=self.metadata.path,
                name=self.metadata.name,
                type_=self.metadata.type,
                source=FileSource.SHARE,
                expire_datetime_utc=expire_define["expire_datetime_utc"],
                expire_days=expire_define["expire_days"],
                access_code=expire_define["access_code"],
            )
            if download_url:
                copy_to_clipboard(download_url, message=_("Share link copied."))

    async def on_download_button_click(self):
        if self.metadata.is_dir:
            message = _(
                "You selected a folder. It will be compressed into a **single tar.gz file**. Download **`{name}.tar.gz`**?"
            ).format(name=self.metadata.name)
        else:
            message = _("Download **`{name}`**?").format(name=self.metadata.name)
        confirm = await ConfirmDialog(_("Confirm Download"), message).open()
        if confirm:
            download_url = await generate_download_url(
                current_user=self.current_user,
                target_path=self.metadata.path,
                name=self.metadata.name,
                type_=self.metadata.type,
                source=FileSource.DOWNLOAD,
            )
            if download_url:
                ui.navigate.to(download_url)


class MediaType(Enum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    PDF = "pdf"
    TEXT = "text"
    MARKDOWN = "markdown"
    CSV = "csv"
    OFFICE = "office"
    UNSUPPORTED = "unsupported"


IMAGE_PREVIEW_EXTS = {
    ".jpeg",
    ".jpg",
    ".png",
    ".svg",
    ".gif",
    ".webp",
    ".bmp",
    ".tiff",
    ".ico",
}
VIDEO_PREVIEW_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
AUDIO_PREVIEW_EXTS = {".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a"}
MARKDOWN_PREVIEW_EXTS = {".md", ".markdown"}
CSV_PREVIEW_EXTS = {".csv", ".tsv"}
TEXT_PREVIEW_EXTS = {
    ".txt",
    ".log",
    ".env",
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".go",
    ".rs",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".php",
    ".rb",
    ".swift",
    ".kt",
    ".kts",
    ".vue",
    ".svelte",
    ".html",
    ".htm",
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".json",
    ".jsonc",
    ".json5",
    ".xml",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".properties",
    ".sql",
    ".sh",
    ".bash",
    ".zsh",
    ".ps1",
    ".bat",
    ".dockerfile",
}
TEXT_PREVIEW_FILENAMES = {
    ".dockerignore",
    ".editorconfig",
    ".env",
    ".env.example",
    ".gitattributes",
    ".gitignore",
    "dockerfile",
    "makefile",
    "requirements.txt",
}
OFFICE_PREVIEW_EXTS = {
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".odt",
    ".ods",
    ".odp",
    ".rtf",
}
MAX_TEXT_PREVIEW_BYTES = 1024 * 1024
MAX_HIGHLIGHT_CHARS = 200_000
MAX_JSON_HIGHLIGHT_CHARS = 80_000
MAX_HIGHLIGHT_LINE_CHARS = 20_000
OFFICE_PREVIEW_CACHE_VERSION = "v2-cjk-fonts"
CODE_PREVIEW_CSS = """
  .stardrive-code-preview pre,
  .stardrive-markdown-preview pre {
    margin: 0;
    border: 1px solid rgba(17, 24, 39, 0.12);
    border-radius: 8px;
    background: #f6f8fa;
    color: #24292f;
  }
  .stardrive-code-preview code,
  .stardrive-markdown-preview pre code {
    display: block;
    min-width: max-content;
    padding: 1rem;
    font-size: 0.875rem;
    line-height: 1.55;
    white-space: pre;
  }
  .stardrive-code-preview code.hljs,
  .stardrive-markdown-preview pre code.hljs {
    background: transparent;
  }
  .stardrive-code-preview-wrap code {
    min-width: 0;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    word-break: break-word;
  }
  .stardrive-markdown-preview pre {
    overflow-x: auto;
  }
  .body--dark .stardrive-code-preview pre,
  .body--dark .stardrive-markdown-preview pre {
    border-color: rgba(255, 255, 255, 0.14);
    background: #111827;
    color: #e5e7eb;
  }
  .body--dark .stardrive-code-preview code.hljs,
  .body--dark .stardrive-markdown-preview pre code.hljs {
    color: #e5e7eb;
  }
"""
CODE_PREVIEW_STYLE_JS = """
(() => {
  if (!document.getElementById('stardrive-highlight-style')) {
    const style = document.createElement('style');
    style.id = 'stardrive-highlight-style';
    style.textContent = __CODE_PREVIEW_CSS__;
    document.head.appendChild(style);
  }
  return true;
})();
""".replace(
    "__CODE_PREVIEW_CSS__", json.dumps(CODE_PREVIEW_CSS)
)
HIGHLIGHT_RUNTIME_JS = """
(() => {
  const styleHref = 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.11.1/styles/github.min.css';
  const scriptSrc = 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.11.1/highlight.min.js';
  const maxHighlightChars = 200000;
  const maxLineChars = 20000;
  if (!document.getElementById('stardrive-highlight-theme')) {
    const link = document.createElement('link');
    link.id = 'stardrive-highlight-theme';
    link.rel = 'stylesheet';
    link.href = styleHref;
    document.head.appendChild(link);
  }
  if (!document.getElementById('stardrive-highlight-style')) {
    const style = document.createElement('style');
    style.id = 'stardrive-highlight-style';
    style.textContent = __CODE_PREVIEW_CSS__;
    document.head.appendChild(style);
  }
  const shouldSkipBlock = (block) => {
    const text = block.textContent || '';
    return text.length > maxHighlightChars || text.split('\\n').some((line) => line.length > maxLineChars);
  };
  const collectBlocks = (root = document) => Array.from(
    root.querySelectorAll(
      '.stardrive-code-preview code[data-stardrive-highlight="1"], ' +
      '.stardrive-markdown-preview pre code:not([data-stardrive-highlighted])'
    )
  ).filter((block) => block.dataset.stardriveHighlighted !== '1');
  const highlight = (root = document) => {
    if (!window.hljs) return;
    const blocks = collectBlocks(root);
    const processBatch = () => {
      const deadline = performance.now() + 24;
      while (blocks.length && performance.now() < deadline) {
        const block = blocks.shift();
        if (block.dataset.stardriveHighlighted === '1') continue;
        if (!shouldSkipBlock(block)) window.hljs.highlightElement(block);
        block.dataset.stardriveHighlighted = '1';
      }
      if (blocks.length) setTimeout(processBatch, 16);
    };
    setTimeout(processBatch, 0);
  };
  highlight();
  if (window.stardriveHighlightObserver) return true;
  window.stardriveHighlightObserver = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      for (const node of mutation.addedNodes) {
        if (node.nodeType === Node.ELEMENT_NODE) highlight(node);
      }
    }
  });
  window.stardriveHighlightObserver.observe(document.body, { childList: true, subtree: true });
  if (window.hljs) {
    highlight();
    return true;
  }
  let script = document.querySelector(`script[src="${scriptSrc}"]`);
  if (!script) {
    script = document.createElement('script');
    script.src = scriptSrc;
    script.onload = () => highlight();
    document.head.appendChild(script);
    return true;
  }
  script.addEventListener('load', () => highlight(), { once: true });
  return true;
})();
""".replace(
    "__CODE_PREVIEW_CSS__", json.dumps(CODE_PREVIEW_CSS)
)
HIGHLIGHT_LANGUAGE_BY_SUFFIX = {
    ".bash": "bash",
    ".bat": "dos",
    ".c": "c",
    ".cc": "cpp",
    ".cfg": "ini",
    ".conf": "nginx",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".css": "css",
    ".dockerfile": "dockerfile",
    ".env": "properties",
    ".go": "go",
    ".h": "cpp",
    ".hpp": "cpp",
    ".htm": "html",
    ".html": "html",
    ".ini": "ini",
    ".java": "java",
    ".js": "javascript",
    ".json": "json",
    ".json5": "json",
    ".jsonc": "json",
    ".jsx": "javascript",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".less": "less",
    ".log": "plaintext",
    ".php": "php",
    ".properties": "properties",
    ".ps1": "powershell",
    ".py": "python",
    ".rb": "ruby",
    ".rs": "rust",
    ".sass": "scss",
    ".scss": "scss",
    ".sh": "bash",
    ".sql": "sql",
    ".svelte": "xml",
    ".swift": "swift",
    ".toml": "ini",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".vue": "xml",
    ".xml": "xml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".zsh": "bash",
}
HIGHLIGHT_LANGUAGE_BY_FILENAME = {
    ".dockerignore": "dockerfile",
    ".editorconfig": "ini",
    ".env": "properties",
    ".env.example": "properties",
    ".gitattributes": "plaintext",
    ".gitignore": "plaintext",
    "dockerfile": "dockerfile",
    "makefile": "makefile",
    "requirements.txt": "plaintext",
}


def detect_preview_media_type(suffix: str) -> MediaType:
    suffix = suffix.lower()
    if suffix in TEXT_PREVIEW_FILENAMES:
        return MediaType.TEXT
    if suffix in IMAGE_PREVIEW_EXTS:
        return MediaType.IMAGE
    if suffix in VIDEO_PREVIEW_EXTS:
        return MediaType.VIDEO
    if suffix in AUDIO_PREVIEW_EXTS:
        return MediaType.AUDIO
    if suffix == ".pdf":
        return MediaType.PDF
    if suffix in MARKDOWN_PREVIEW_EXTS:
        return MediaType.MARKDOWN
    if suffix in CSV_PREVIEW_EXTS:
        return MediaType.CSV
    if suffix in TEXT_PREVIEW_EXTS:
        return MediaType.TEXT
    if suffix in OFFICE_PREVIEW_EXTS:
        return MediaType.OFFICE
    return MediaType.UNSUPPORTED


def detect_highlight_language(path: Path) -> str | None:
    name = path.name.lower()
    return HIGHLIGHT_LANGUAGE_BY_FILENAME.get(
        name, HIGHLIGHT_LANGUAGE_BY_SUFFIX.get(path.suffix.lower())
    )


def ensure_highlight_assets():
    async def apply_highlighting():
        await ui.run_javascript(HIGHLIGHT_RUNTIME_JS)

    ui.timer(0.1, apply_highlighting, once=True)


def ensure_code_preview_style():
    async def apply_style():
        await ui.run_javascript(CODE_PREVIEW_STYLE_JS)

    ui.timer(0.1, apply_style, once=True)


def should_highlight_text(path: Path, text: str, truncated: bool) -> bool:
    language = detect_highlight_language(path)
    if language is None or truncated:
        return False

    text_length = len(text)
    if text_length > MAX_HIGHLIGHT_CHARS:
        return False
    if language == "json" and text_length > MAX_JSON_HIGHLIGHT_CHARS:
        return False
    return not any(len(line) > MAX_HIGHLIGHT_LINE_CHARS for line in text.splitlines())


def build_office_preview_cache_path(source_path: Path) -> Path:
    source_path = source_path.resolve()
    stat = source_path.stat()
    cache_key = hashlib.sha256(
        (
            f"{OFFICE_PREVIEW_CACHE_VERSION}:"
            f"{source_path.as_posix()}:{stat.st_mtime_ns}:{stat.st_size}"
        ).encode("utf-8")
    ).hexdigest()
    return PREVIEW_CACHE_DIR / f"{cache_key}.pdf"


def should_render_image_information(
    is_streaming_backend: bool, image_info: dict[str, object]
) -> bool:
    """Image metadata is only available when the source is a local file."""
    return not is_streaming_backend and bool(image_info)


class MediaDialog(Dialog):

    def __init__(self, file_manager: StorageManager, media_path: Path):
        super().__init__()

        self.file_manager = file_manager
        self.remote_path = str(media_path)
        self.is_streaming_backend = self.file_manager.backend_name != "LocalStorage"
        self.media_path = (
            Path(media_path)
            if self.is_streaming_backend
            else self.file_manager.get_full_path(str(media_path))
        )
        self.preview_url = (
            create_storage_preview_url(self.file_manager.user_id, self.remote_path)
            if self.is_streaming_backend
            else None
        )
        self.suffix = media_path.suffix.lower()
        self.media_type = self._detect_media_type()
        self.preview_error: str | None = None

        self.dialog = ui.dialog().props(self.dialog_props)

        self.keyboard = ui.keyboard(on_key=self.handle_key)
        self.keyboard.active = True

        # refs
        self.video_ref = None
        self.audio_ref = None

        # image only
        self.image_info: dict[str, object] = {}
        if self.media_type == MediaType.IMAGE and not self.is_streaming_backend:
            try:
                self.image_info = get_image_info(self.media_path, str(media_path))
            except Exception:
                self.image_info = {}

    # -------------------------
    # type detect
    # -------------------------
    def _detect_media_type(self) -> MediaType:
        media_type = detect_preview_media_type(self.suffix)
        if media_type == MediaType.UNSUPPORTED:
            return detect_preview_media_type(Path(self.media_path).name)
        return media_type

    # -------------------------
    # keyboard
    # -------------------------
    def handle_key(self, e: KeyEventArguments):
        if not e.action.keydown:
            return

        if e.key.escape or e.key.space:
            self.dialog.submit(None)

    # -------------------------
    # open
    # -------------------------
    async def open(self):
        with (
            self.dialog,
            ui.card().tight().classes("w-[1200px] max-w-[90vw] overflow-hidden"),
        ):
            if self.media_type == MediaType.IMAGE:
                self._render_image()
            elif self.media_type == MediaType.VIDEO:
                self._render_video()
            elif self.media_type == MediaType.AUDIO:
                self._render_audio()
            elif self.media_type == MediaType.PDF:
                self._render_pdf(self.media_path)
            elif self.media_type == MediaType.MARKDOWN:
                self._render_markdown()
            elif self.media_type == MediaType.CSV:
                self._render_csv()
            elif self.media_type == MediaType.TEXT:
                self._render_text()
            elif self.media_type == MediaType.OFFICE:
                await self._render_office()
            else:
                self._render_unsupported()

        return await self.dialog

    def _render_header(self, title: str):
        with ui.row().classes("w-full items-center justify-between px-4 py-2"):
            ui.label(title).classes("font-bold break-all")
            ui.button(icon="close", on_click=lambda: self.dialog.submit(None)).props(
                "flat dense"
            )

    def _render_text_header(self, title: str, preview_id: str):
        async def toggle_wrap(event):
            await ui.run_javascript(
                (
                    "document.getElementById("
                    f"{json.dumps(preview_id)}"
                    ")?.classList.toggle('stardrive-code-preview-wrap', "
                    f"{json.dumps(bool(event.value))}"
                    ");"
                )
            )

        with ui.row().classes("w-full items-center justify-between gap-3 px-4 py-2"):
            ui.label(title).classes("font-bold break-all min-w-0")
            with ui.row(wrap=False).classes("items-center gap-2 shrink-0"):
                ui.switch(_("Wrap lines"), value=False, on_change=toggle_wrap).props(
                    "dense"
                )
                ui.button(
                    icon="close", on_click=lambda: self.dialog.submit(None)
                ).props("flat dense")

    def _render_image(self):
        ui.image(self.preview_url or self.media_path).classes(
            "w-full max-h-[600px] object-contain"
        )

        if not should_render_image_information(
            self.is_streaming_backend, self.image_info
        ):
            return

        with ui.card_section().classes("w-full"):
            with ui.row(wrap=False).classes("w-full items-start gap-6"):
                # 左侧信息
                with ui.column().classes("flex-1 min-w-0"):
                    label(_("Image Information"), extra_classes="text-lg font-bold")

                    with ui.column().classes("gap-2 text-sm"):
                        for k, v in self.image_info.items():
                            if k == _("GPS"):
                                continue
                            with ui.row().classes("gap-2 break-all"):
                                ui.label(k).classes("w-24 shrink-0 font-medium")
                                ui.label(str(v)).classes("flex-1")

                # 右侧地图
                if _("GPS") in self.image_info:
                    gps = self.image_info[_("GPS")]
                    with ui.column().classes("flex-1 min-w-[300px]"):
                        label(_("Location"), extra_classes="text-lg font-bold")

                        m = ui.leaflet(
                            center=(gps["Latitude"], gps["Longitude"]),
                            zoom=15,
                        ).classes("w-full rounded-l overflow-hidden")
                        m.marker(latlng=m.center)

    def _render_video(self):
        self._render_header(Path(self.media_path).name)
        self.video_ref = ui.video(
            self.preview_url or self.media_path,
            controls=True,
            autoplay=False,
        ).classes("w-full max-h-[600px] object-contain bg-black")

    def _render_audio(self):
        self._render_header(Path(self.media_path).name)
        with ui.column().classes("w-full items-center gap-4 p-6"):
            ui.icon("music_note", size="64px")
            ui.label(Path(self.media_path).name).classes("text-lg")

            self.audio_ref = ui.audio(
                self.preview_url or self.media_path,
                controls=True,
                autoplay=False,
            ).classes("w-full")

    def _render_pdf(self, pdf_path: Path | str):
        self._render_header(Path(pdf_path).name)
        preview_url = (
            self.preview_url
            if self.is_streaming_backend
            else create_preview_file_url(pdf_path)
        )
        ui.html(
            f'<iframe src="{preview_url}" class="w-full h-[75vh] border-0"></iframe>',
            sanitize=False,
        ).classes("w-full")

    def _read_text_preview(self) -> tuple[str, bool]:
        if self.is_streaming_backend:
            data = b"".join(
                self.file_manager.download_file_with_stream(
                    self.remote_path, 0, MAX_TEXT_PREVIEW_BYTES + 1
                )
            )
            truncated = len(data) > MAX_TEXT_PREVIEW_BYTES
            return (
                data[:MAX_TEXT_PREVIEW_BYTES].decode("utf-8", errors="replace"),
                truncated,
            )
        with self.media_path.open("rb") as file:
            data = file.read(MAX_TEXT_PREVIEW_BYTES + 1)
        truncated = len(data) > MAX_TEXT_PREVIEW_BYTES
        text = data[:MAX_TEXT_PREVIEW_BYTES].decode("utf-8", errors="replace")
        return text, truncated

    def _render_text_limit_notice(self, truncated: bool):
        if truncated:
            ui.label(
                _("Preview is limited to the first {size} MB.").format(
                    size=MAX_TEXT_PREVIEW_BYTES // (1024 * 1024)
                )
            ).classes("text-xs text-orange-600 px-4 pb-2")

    def _render_text(self):
        preview_id = (
            "stardrive-code-preview-"
            + hashlib.sha256(self.media_path.as_posix().encode("utf-8")).hexdigest()[
                :12
            ]
        )
        self._render_text_header(Path(self.media_path).name, preview_id)
        text, truncated = self._read_text_preview()
        self._render_text_limit_notice(truncated)
        should_highlight = should_highlight_text(self.media_path, text, truncated)
        if should_highlight:
            ensure_highlight_assets()
        else:
            ensure_code_preview_style()
        escaped = html.escape(text)
        language = detect_highlight_language(self.media_path)
        code_class = f"language-{language}" if language else ""
        highlight_attr = ' data-stardrive-highlight="1"' if should_highlight else ""
        ui.html(
            (
                f'<div id="{preview_id}" class="stardrive-code-preview w-full h-[75vh] overflow-auto">'
                f'<pre><code class="{code_class}"{highlight_attr}>{escaped}</code></pre>'
                "</div>"
            ),
            sanitize=False,
        ).classes("w-full")

    def _render_markdown(self):
        self._render_header(Path(self.media_path).name)
        text, truncated = self._read_text_preview()
        self._render_text_limit_notice(truncated)
        ensure_highlight_assets()
        with ui.scroll_area().classes("w-full h-[75vh] px-4"):
            ui.markdown(text).classes("stardrive-markdown-preview w-full")

    def _render_csv(self):
        self._render_header(Path(self.media_path).name)
        text, truncated = self._read_text_preview()
        self._render_text_limit_notice(truncated)

        delimiter = "\t" if self.suffix == ".tsv" else ","
        rows = list(csv.reader(text.splitlines(), delimiter=delimiter))
        if not rows:
            ui.label(_("This file is empty.")).classes("p-6")
            return

        headers = rows[0][:20]
        body_rows = rows[1:201]
        if not headers:
            self._render_text()
            return

        columns = [
            {
                "name": f"col_{index}",
                "label": header or f"Column {index + 1}",
                "field": f"col_{index}",
                "align": "left",
            }
            for index, header in enumerate(headers)
        ]
        table_rows = [
            {
                f"col_{index}": row[index] if index < len(row) else ""
                for index in range(len(headers))
            }
            for row in body_rows
        ]
        ui.table(columns=columns, rows=table_rows, pagination=20).classes(
            "w-full h-[75vh]"
        )

    async def _render_office(self):
        if not find_libreoffice_command():
            self._render_libreoffice_installation_guide()
            return

        if self.is_streaming_backend:
            self.preview_url = create_storage_preview_url(
                self.file_manager.user_id, self.remote_path, office=True
            )
            self._render_pdf(self.media_path)
            return
        pdf_path, error = await asyncio.to_thread(self._convert_office_to_pdf)
        if error:
            self._render_unsupported(error)
            return
        self._render_pdf(pdf_path)

    def _convert_office_to_pdf(self) -> tuple[Path | None, str | None]:
        converter = find_libreoffice_command()
        if not converter:
            return None, _(
                "Preview is not available for {suffix} files because LibreOffice is not installed."
            ).format(suffix=self.suffix or _("this file type"))

        cache_path = build_office_preview_cache_path(self.media_path)
        if cache_path.exists():
            return cache_path, None

        PREVIEW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=PREVIEW_CACHE_DIR) as temp_dir:
            command = [
                converter,
                "--headless",
                "--nologo",
                "--nofirststartwizard",
                "--convert-to",
                "pdf",
                "--outdir",
                temp_dir,
                self.media_path.as_posix(),
            ]
            try:
                subprocess.run(
                    command,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            except subprocess.TimeoutExpired:
                return None, _("Preview conversion timed out.")
            except subprocess.CalledProcessError as error:
                detail = (error.stderr or error.stdout or "").strip()
                return None, _(
                    "Failed to convert this file for preview: {error}"
                ).format(error=detail or _("unknown error"))

            generated_pdf = Path(temp_dir) / f"{self.media_path.stem}.pdf"
            if not generated_pdf.exists():
                candidates = list(Path(temp_dir).glob("*.pdf"))
                if not candidates:
                    return None, _("Failed to convert this file for preview.")
                generated_pdf = candidates[0]

            shutil.move(generated_pdf, cache_path)
            return cache_path, None

    def _render_libreoffice_installation_guide(self):
        self._render_header(Path(self.media_path).name)
        with ui.column().classes("w-full items-center gap-5 p-8 text-center"):
            ui.icon("description", size="64px").style(f"color: {theme().warning}")
            with ui.column().classes("items-center gap-1"):
                ui.label(_("Office preview needs LibreOffice")).classes(
                    "text-xl font-bold"
                )
                ui.label(
                    _(
                        "LibreOffice is required on the StarDrive server to preview Word, Excel, and PowerPoint files."
                    )
                ).classes("text-sm text-gray-600 dark:text-gray-300 max-w-[560px]")

            with ui.card().classes(
                "w-full max-w-[560px] text-left bg-blue-50 dark:bg-blue-950"
            ):
                with ui.row(wrap=False).classes("items-start gap-3"):
                    ui.icon("info", size="20px").style(f"color: {theme().info}")
                    ui.label(
                        _(
                            "This is a server configuration step. Visitors do not need to install anything on their own computers."
                        )
                    ).classes("text-sm")

            with ui.column().classes("w-full max-w-[560px] gap-3 text-left"):
                ui.label(
                    _("Ask a server administrator to install LibreOffice:")
                ).classes("font-medium")
                for platform, command in (
                    ("macOS", "brew install --cask libreoffice"),
                    (
                        "Ubuntu / Debian",
                        "sudo apt update && sudo apt install -y libreoffice libreoffice-calc",
                    ),
                    (
                        "Fedora / RHEL",
                        "sudo dnf install -y libreoffice libreoffice-calc",
                    ),
                ):
                    with ui.column().classes("gap-1"):
                        ui.label(platform).classes("text-sm font-medium")
                        ui.label(command).classes(
                            "w-full rounded bg-gray-100 dark:bg-gray-800 px-3 py-2 "
                            "font-mono text-xs break-all"
                        )
                ui.label(
                    _(
                        "For Docker deployments, rebuild and redeploy using this project's Dockerfile; it already includes LibreOffice."
                    )
                ).classes("text-sm text-gray-600 dark:text-gray-300")

            ui.label(
                _("After installation, restart StarDrive and reopen this file.")
            ).classes("text-sm text-gray-600 dark:text-gray-300")
            ui.button(_("Close"), on_click=lambda: self.dialog.submit(None)).props(
                "flat"
            )

    def _render_unsupported(self, message: str | None = None):
        suffix = self.suffix or _("unknown")
        self._render_header(Path(self.media_path).name)
        with ui.column().classes("w-full items-center gap-4 p-8 text-center"):
            ui.icon("visibility_off", size="64px").classes("text-orange-500")
            ui.label(_("Preview unavailable")).classes("text-xl font-bold")
            ui.label(
                message
                or _("Preview is not available for this file type: {suffix}").format(
                    suffix=suffix
                )
            ).classes("text-sm text-gray-600 dark:text-gray-300")
            ui.button(_("Close"), on_click=lambda: self.dialog.submit(None)).props(
                "flat"
            )
