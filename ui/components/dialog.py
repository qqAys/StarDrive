import asyncio
from datetime import datetime, timezone, date, time
from pathlib import Path
from typing import Optional, Callable

from nicegui import ui, events

from schemas.file_schema import FILE_NAME_FORBIDDEN_CHARS, FileMetadata, DirMetadata
from services.file_service import (
    get_user_share_links,
    delete_download_link,
    StorageManager,
    get_file_icon,
    generate_download_url,
)
from services.user_service import get_user_timezone
from ui.components.clipboard import copy_to_clipboard
from ui.components.notify import notify
from utils import _, bytes_to_human_readable, timestamp_to_human_readable


class Dialog:
    dialog_props = 'backdrop-filter="blur(2px) brightness(90%)"'
    title_class = "text-lg font-bold break-words max-w-full"

    def __init__(self):
        self.dialog = ui.dialog().props(self.dialog_props)

    async def open(self):
        r = await self.dialog
        return r


class SearchDialog(Dialog):

    PAGE_SIZE = 30

    def __init__(self, file_service: StorageManager, current_path: Path):
        super().__init__()
        self.search_input: Optional[ui.input] = None
        self.file_service = file_service
        self.current_path = current_path

        self.last_query: Optional[str] = None
        self.results_list: Optional[ui.list] = None

        self.last_query: Optional[str] = None
        self.offset = 0
        self.loading = False
        self.has_more = True

        self.search_task: Optional[asyncio.Task] = None

    async def open(self) -> Optional[FileMetadata | DirMetadata | None]:
        with self.dialog, ui.card().tight().classes("w-[800px] h-[600px]"):
            with ui.row().classes("w-full items-center px-4"):
                self.search_input = (
                    ui.input(
                        label=f"Search in {self.current_path.name}",
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

        r = await self.dialog
        return r

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

        results = await self.file_service.search(
            query=self.last_query,
            remote_path=str(self.current_path),
            offset=self.offset,
            limit=self.PAGE_SIZE,
        )

        if not results:
            self.has_more = False
            self.loading = False

            with self.results_list:
                with ui.item().props("disabled"):
                    with ui.column().classes("w-full items-center gap-1"):
                        ui.button(text=_("No more results."), icon="search_off").props(
                            "flat no-caps"
                        )
                        ui.markdown(
                            _(
                                "If you still can't find it, try searching in a **different directory**."
                            )
                        ).classes("text-xs my-0 py-0")
                        ui.markdown(
                            _("Current directory: **{}**").format(self.current_path)
                        ).classes("text-xs my-0 py-0")
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
        self.loading = False

    async def on_scroll(self, e: events.ScrollEventArguments):
        if e.vertical_percentage == 1:
            await self.load_more()


class InputDialog(Dialog):
    def __init__(
        self, title: str, input_label: str, input_value: str = "", message: str = None
    ):
        super().__init__()
        self.title = title
        self.message = message
        self.input_label = input_label
        self.input_value = input_value

        self.dialog = ui.dialog().props(self.dialog_props)

    async def open(self):
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
                    on_click=lambda: self.dialog.submit(input_component.value),
                    color="green",
                )
                ui.button(_("Cancel"), on_click=lambda: self.dialog.submit(None))

        r = await self.dialog
        return r


class ConfirmDialog(Dialog):

    def __init__(self, title: str, message: str | list = None, warning: bool = False):
        super().__init__()
        self.title = title
        self.message = message
        self.warning = warning

        self.dialog = ui.dialog().props(self.dialog_props)

    async def open(self):
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
                ui.button(_("Cancel"), on_click=lambda: self.dialog.submit(False))

        r = await self.dialog
        return r


class RenameDialog(InputDialog):
    def __init__(self, current_name: str, old_name: str):
        super().__init__(
            title=_("Rename {}").format(current_name),
            input_label=_("New name"),
            input_value=old_name,
        )
        self.old_name = old_name

    async def open(self):
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

            def is_same(a, b):
                return a == b

            async def on_confirm():
                new_val = input_component.value.strip()
                if not new_val:
                    notify.warning(_("New name cannot be empty"))
                    return None
                if is_same(new_val, self.old_name):
                    notify.warning(_("New name cannot be the same as the current name"))
                    return None
                if any(char in new_val for char in FILE_NAME_FORBIDDEN_CHARS):
                    notify.warning(
                        f"File name cannot contain any of the following characters: {FILE_NAME_FORBIDDEN_CHARS}"
                    )
                    return None
                if new_val.endswith("."):
                    notify.warning(_("File name cannot end with a dot"))
                    return None

                confirm = await ConfirmDialog(
                    title=_("Confirm Rename"),
                    message=_(
                        "Are you sure you want to rename **`{}`** to **`{}`** ?"
                    ).format(self.old_name, new_val),
                ).open()

                if confirm:
                    return self.dialog.submit(new_val)
                return None

            with ui.row().classes("w-full justify-between"):
                ui.button(_("Confirm"), on_click=on_confirm, color="green")
                ui.button(_("Cancel"), on_click=lambda: self.dialog.submit(None))

        r = await self.dialog
        return r


class ShareDialog(Dialog):
    def __init__(self, file_name: str):
        super().__init__()
        self.title = _("Share {}").format(file_name)
        self.file_name = file_name

        self.dialog = ui.dialog().props(self.dialog_props)

    async def open(self):
        with self.dialog, ui.card().classes("w-full"):
            ui.label(self.title).classes(self.title_class)

            user_share_links = get_user_share_links(self.file_name)
            if user_share_links:
                ui.separator()
                ui.label(_("Valid sharing links")).classes("text-base font-bold")

                all_share_link_dropdown_button: dict[str, ui.dropdown_button] = {}

                def delete_share_link(download_id: str) -> bool:
                    try:
                        delete_download_link(download_id)
                        all_share_link_dropdown_button[download_id].remove(
                            all_share_link_dropdown_button[download_id]
                        )
                        notify.success(_("Share link deleted"))
                    except Exception as e:
                        notify.error(
                            _("Failed to delete share link: {}").format(str(e))
                        )
                        return False
                    return True

                with ui.row().classes("w-full justify-between"):
                    for share_link in user_share_links:
                        link_url = share_link["info"]["url"]
                        link_expire_time = (
                            datetime.fromisoformat(share_link["info"]["exp"])
                            .astimezone(get_user_timezone())
                            .strftime("%Y-%m-%d %H:%M:%S")
                        )
                        with (
                            ui.dropdown_button(
                                _("EXP: {}").format(link_expire_time),
                                icon="share",
                                split=True,
                                on_click=lambda url=link_url: ui.navigate.to(
                                    url, new_tab=True
                                ),
                                auto_close=True,
                            )
                            .props("no-caps dense")
                            .classes("md:w-auto w-full") as dropdown_button
                        ):
                            with ui.row(wrap=False).classes("w-full justify-between"):
                                ui.button(
                                    _("Copy"),
                                    icon="content_copy",
                                    on_click=lambda: copy_to_clipboard(
                                        link_url,
                                        message=_("Share link copied to clipboard."),
                                    ),
                                ).classes("w-full").props("flat dense")
                                ui.button(
                                    _("Delete"),
                                    icon="delete",
                                    on_click=lambda d_id=share_link[
                                        "id"
                                    ]: delete_share_link(d_id),
                                ).classes("w-full").props("flat dense")
                        all_share_link_dropdown_button[share_link["id"]] = (
                            dropdown_button
                        )

                ui.separator()
                ui.label(_("Create new sharing link")).classes("text-base font-bold")

            user_timezone = get_user_timezone()
            current_time_local = datetime.now(user_timezone)

            expire_type = ui.toggle(
                [_("Expire after"), _("Expire after days")], value=_("Expire after")
            )

            with ui.row().classes("w-full justify-between") as datetime_picker:
                date_input = ui.date_input(
                    _("Expire date"), value=current_time_local.strftime("%Y-%m-%d")
                ).classes("md:w-auto w-full")
                date_input.picker.props[":options"] = (
                    f'date => date >= "{current_time_local.strftime("%Y/%m/%d")}"'
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

            def on_expire_type_change(e: events.ValueChangeEventArguments):
                value = e.value
                days_picker.set_visibility(value == _("Expire after days"))
                datetime_picker.set_visibility(value == _("Expire after"))

            expire_type.on_value_change(on_expire_type_change)

            def on_confirm():
                if expire_type.value == _("Expire after"):
                    if not date_input.value or not time_input.value:
                        notify.warning(_("Please select a valid expire time"))
                        return None
                    selected_date = date.fromisoformat(date_input.value)
                    selected_time_parts = time_input.value.split(":")
                    selected_time = time(
                        int(selected_time_parts[0]),  # hours
                        int(selected_time_parts[1]),  # minutes
                    )

                    expire_datetime_naive = datetime.combine(
                        selected_date, selected_time
                    )
                    expire_datetime = expire_datetime_naive.replace(
                        tzinfo=user_timezone
                    ).astimezone(timezone.utc)

                    if expire_datetime < current_time_local.astimezone(timezone.utc):
                        notify.warning(_("Expire date cannot be before now"))
                        return None
                    return self.dialog.submit(
                        {
                            "expire_datetime_utc": expire_datetime,
                            "expire_days": None,
                        }
                    )
                elif expire_type.value == _("Expire after days"):
                    return self.dialog.submit(
                        {
                            "expire_datetime_utc": None,
                            "expire_days": int(days.value),
                        }
                    )
                return None

            with ui.row().classes("w-full justify-between"):
                ui.button(
                    _("Confirm"),
                    on_click=on_confirm,
                    color="green",
                )
                ui.button(_("Cancel"), on_click=lambda: self.dialog.submit(None))

        r = await self.dialog
        return r


class MoveDialog(Dialog):
    """
    移动对话框
    用户选择目标文件夹后，返回路径
    """

    def __init__(self, file_service: StorageManager, files: list, current_path: Path):
        super().__init__()
        self.title_label: Optional[ui.label] = None

        self.file_service = file_service
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

            with dir_table.add_slot("top-left"):
                with ui.row().classes("items-center gap-x-0"):
                    # 返回上一级目录按钮
                    ui.button(
                        icon="arrow_upward",
                        on_click=lambda: refresh_dir_table(target_path, True),
                    ).props("flat dense").tooltip(_("Back to parent directory"))

            with dir_table.add_slot("no-data"):
                with ui.row().classes("items-center"):
                    ui.icon("warning").classes("text-2xl")
                    ui.label(_("No directories found.")).classes("font-bold")

            dir_table_rows = []

            def refresh_dir_table(path: Path, parent: bool = False):
                nonlocal dir_table_rows, target_path
                if parent:
                    path = path.parent

                self.title_label.text = _("Move {} to {}").format(
                    (
                        f"{len(self.files)} items"
                        if len(self.files) > 1
                        else self.files[0]
                    ),
                    str(path),
                )
                dir_table_rows = []
                for meta_data in self.file_service.list_files(str(path)):
                    if meta_data.is_dir:
                        dir_table_rows.append(
                            {
                                "name": f"{get_file_icon(meta_data.type, meta_data.extension)} {meta_data.name}",
                                "path": meta_data.path,
                            }
                        )
                dir_table.rows = dir_table_rows
                target_path = path

            refresh_dir_table(target_path)

            async def handle_row_double_click(e: events.GenericEventArguments):
                click_event_params, click_row, click_index = e.args
                refresh_dir_table(Path(click_row["path"]))
                return

            dir_table.on("row-dblclick", handle_row_double_click)

            with ui.row().classes("w-full justify-between"):
                ui.button(
                    _("Confirm"),
                    on_click=lambda: self.dialog.submit(target_path),
                    color="green",
                )
                ui.button(_("Cancel"), on_click=lambda: self.dialog.submit(None))

        r = await self.dialog
        return r


class MetadataDialog(Dialog):
    def __init__(
        self,
        current_path: Path,
        metadata: FileMetadata | DirMetadata,
        file_service: StorageManager,
        refresh_browser_func: Callable,
    ):
        super().__init__()
        self.current_path = current_path
        self.metadata = metadata
        self.is_dir = self.metadata.is_dir
        self.file_service = file_service
        self.refresh_browser = refresh_browser_func

        self.size_label: ui.label | None = None
        self.calc_btn: ui.button | None = None

        self.user_timezone = get_user_timezone()

        self.dialog = ui.dialog().props(self.dialog_props)

    async def open(self):
        with self.dialog, ui.card().classes("w-full"):
            with ui.row().classes("w-full justify-between"):
                ui.label(_("Metadata info")).classes(self.title_class)
                ui.button(
                    icon="close", on_click=lambda: self.dialog.submit(None)
                ).props("flat dense")

            with ui.card().props("bordered flat").classes("w-full"):
                with ui.list().props("dense separator").classes("w-full"):
                    for k, v in {
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
                        _("Accessed At"): timestamp_to_human_readable(
                            self.metadata.accessed_at, self.user_timezone
                        ),
                        _("Created At"): timestamp_to_human_readable(
                            self.metadata.created_at, self.user_timezone
                        ),
                        _("Modified At"): timestamp_to_human_readable(
                            self.metadata.modified_at, self.user_timezone
                        ),
                        _("Status Changed At"): timestamp_to_human_readable(
                            self.metadata.status_changed_at, self.user_timezone
                        ),
                    }.items():
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

        r = await self.dialog
        return r

    async def calculate_dir_size(self):
        self.size_label.text = _("Calculating...")
        dir_size = await self.file_service.get_directory_size(self.metadata.path)
        self.size_label.text = bytes_to_human_readable(dir_size)

    async def on_delete_button_click(self):
        confirm = await ConfirmDialog(
            _("Confirm Delete"),
            _("Are you sure you want to delete **`{}`**").format(self.metadata.name),
            warning=True,
        ).open()
        if confirm:
            try:
                self.file_service.delete_file(self.metadata.path)
                notify.success(_("Delete successful"))
            except Exception as e:
                notify.error(e)
        else:
            return
        await self.refresh_browser()

    async def on_rename_button_click(self):
        new_name = await RenameDialog(
            current_name=self.metadata.name, old_name=self.metadata.name
        ).open()
        if new_name:
            new_path = Path(self.metadata.path).parent / new_name
            if self.file_service.exists(new_path):
                notify.warning(
                    _(
                        "A file or folder with this name already exists. Please choose a different name."
                    )
                )
                return
            try:
                self.file_service.move_file(self.metadata.path, new_path)
                notify.success(_("Rename successful"))
            except Exception as e:
                notify.error(e)
        else:
            return
        await self.refresh_browser()

    async def on_move_button_click(self):
        target_path = await MoveDialog(
            self.file_service, [self.metadata.name], self.current_path
        ).open()
        if target_path:
            if target_path == self.current_path:
                notify.error(
                    _(
                        "Cannot move items to the same folder. Please select a different destination."
                    )
                )
                return

            try:
                self.file_service.move_file(
                    self.metadata.path, target_path / self.metadata.name
                )
                notify.success(
                    _("Move successful to {}").format(target_path / self.metadata.name)
                )
            except Exception as e:
                notify.error(e)
        else:
            return

        await self.refresh_browser()

    async def on_share_button_click(self):
        expire_define = await ShareDialog(file_name=self.metadata.name).open()
        if expire_define:
            download_url = generate_download_url(
                self.metadata.path,
                self.metadata.name,
                self.metadata.type,
                "share",
                expire_define["expire_datetime_utc"],
                expire_define["expire_days"],
            )
            if not download_url:
                return
            copy_to_clipboard(
                download_url, message=_("Share link copied to clipboard.")
            )
        return

    async def on_download_button_click(self):
        if self.metadata.is_dir:
            confirm = await ConfirmDialog(
                _("Confirm Download"),
                _(
                    "You selected a folder. It will be compressed into a **single tar.gz file** for download. "
                )
                + _("Are you sure you want to download **`{}`**? ").format(
                    self.metadata.name
                ),
            ).open()
        else:
            confirm = await ConfirmDialog(
                _("Confirm Download"),
                _("Are you sure you want to download **`{}`**? ").format(
                    self.metadata.name
                ),
            ).open()

        if confirm:
            download_url = generate_download_url(
                self.metadata.path, self.metadata.name, self.metadata.type, "download"
            )
            if not download_url:
                return
            ui.navigate.to(download_url)
            return
        else:
            return
