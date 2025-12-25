import asyncio
from datetime import datetime, timezone, date, time
from pathlib import Path
from typing import Optional, Callable

from nicegui import ui, events

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
)
from app.services.user_service import get_user_timezone
from app.ui.components.clipboard import copy_to_clipboard
from app.ui.components.notify import notify
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
        with self.dialog, ui.card().tight().classes("w-[800px] h-[600px]"):
            with ui.row().classes("w-full items-center px-4"):
                self.search_input = (
                    ui.input(
                        label=_("Search in {folder}").format(
                            folder=self.current_path.name
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
                    with ui.item_section():
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
                    ui.button(
                        text=_("No more results"),
                        icon="search_off",
                    ).props("flat no-caps")
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
                    color="green",
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
                    color="red" if self.warning else "green",
                )
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
        self.target_root_path = self.file_manager.get_full_path(str(self.target_path))
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
                    _, row, _ = e.args
                    click_path = row["path"]
                    file_name = row["raw_name"]
                    if row["is_dir"]:
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
                _, click_row, _ = e.args
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
                        _(
                            "Extension"
                        ): f"{self.metadata.extension} ({get_file_icon(self.metadata.type, self.metadata.extension)})",
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
                "You selected a folder. It will be compressed into a single tar.gz file. Download **`{name}`**?"
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
