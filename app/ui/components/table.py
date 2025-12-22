from pathlib import Path
from typing import Optional

from nicegui import ui, events
from starlette.formparsers import MultiPartParser

from app.config import settings
from app.core.i18n import _
from app.models.user_model import User
from app.schemas.file_schema import DirMetadata, FileMetadata, FileType, FileSource
from app.services.file_service import (
    StorageManager,
    get_file_icon,
    generate_download_url,
    set_user_last_path,
    validate_filename,
    get_user_last_path,
)
from app.services.user_service import get_user_timezone
from app.ui.components.clipboard import copy_to_clipboard
from app.ui.components.dialog import (
    ConfirmDialog,
    MoveDialog,
    InputDialog,
    SearchDialog,
    MetadataDialog,
)
from app.ui.components.notify import notify
from app.utils.size import bytes_to_human_readable
from app.utils.time import timestamp_to_human_readable

size_sort_js = """(a, b, rowA, rowB) => {
    const isDirA = rowA.type === 'dir';
    const isDirB = rowB.type === 'dir';

    // 目录优先
    if (isDirA && !isDirB) return -1;
    if (!isDirA && isDirB) return 1;

    // 按 raw_size 排序
    return rowA.raw_size - rowB.raw_size;
}"""

MultiPartParser.spool_max_size = settings.MULTIPARTPARSER_SPOOL_MAX_SIZE


class FileBrowserTable:
    def __init__(
        self,
        file_manager: StorageManager,
        current_user: User,
        initial_path: str = ".",
        target_path: str = "",
        upload_component: ui.upload = None,
        upload_dialog: ui.dialog = None,
        upload_dialog_close_button: ui.button = None,
    ):

        self.file_manager = file_manager
        self.current_user = current_user
        self.user_timezone = get_user_timezone()

        self.browser_table: Optional[ui.table] = None
        self.action_column = {
            "sortable": False,
            "name": "action",
            "label": _("Action"),
            "style": "width: 0px",
            "align": "center",
        }

        self.is_select_mode = False
        self.pending_display_metadata_path: Optional[str] = None
        self.edit_button_icon_open = "check_box"
        self.edit_button_icon_close = "check_box_outline_blank"
        self.search_input: Optional[ui.input] = None
        self.edit_button: Optional[ui.button] = None
        self.delete_button: Optional[ui.button] = None
        self.move_button: Optional[ui.button] = None
        self.new_directory_button: Optional[ui.button] = None
        self.upload_button: Optional[ui.button] = None
        self.download_button: Optional[ui.button] = None

        self.upload_component = upload_component
        self.upload_component.on_multi_upload(self.handle_upload)
        self.upload_dialog = upload_dialog
        self.upload_dialog_close_button = upload_dialog_close_button
        self.upload_dialog_close_button.on_click(self.handle_upload_button_click)
        self.on_upload = False

        self.file_list = []

        self._current_path: Path = Path(initial_path, target_path)
        if not get_user_last_path():
            set_user_last_path(self._current_path)

        if not self.file_manager.exists(str(self.current_path)):
            notify.error(_("Path not exists, will go to home dir."))
            self._current_path: Path = Path(initial_path)

        @ui.refreshable
        async def browser_content():
            self.file_list = self.file_manager.list_files(str(self.current_path))

            columns = [
                {
                    "name": "name",
                    "label": _("Name"),
                    "field": "name",
                    "align": "left",
                    "required": True,
                },
                {
                    "name": "type",
                    "label": _("Type"),
                    "field": "type",
                    "classes": "hidden",
                    "headerClasses": "hidden",
                },
                {
                    "name": "extension",
                    "label": _("Extension"),
                    "field": "extension",
                    # "classes": "hidden",
                    # "headerClasses": "hidden",
                    "align": "left",
                    "style": "width: 0px",
                },
                {
                    "name": "size",
                    "label": _("Size"),
                    "field": "size",
                    "required": True,
                    ":sort": size_sort_js,
                    "align": "right",
                    "style": "width: 0px",
                },
                {
                    "name": "created_at",
                    "label": _("Created At"),
                    "classes": "hidden",
                    "headerClasses": "hidden",
                    "field": "created_at",
                    "style": "width: 0px",
                },
                {
                    "name": "updated_at",
                    "label": _("Updated At"),
                    "field": "updated_at",
                    "style": "width: 0px",
                },
                self.action_column,
            ]

            if self.browser_table:
                self.browser_table.clear()

            self.browser_table = ui.table(
                columns=columns,
                rows=[],
                row_key="name",
                title=_("File List"),
                pagination=0,
                column_defaults={
                    "sortable": True,
                    "align": "center",
                },
            ).classes("w-full h-full")

            self.browser_table.pagination = {
                "sortBy": "type",
                "descending": False,
                "page": 1,
                "rowsPerPage": 0 if len(self.file_list) < 50 else 15,
            }

            with self.browser_table.add_slot("no-data"):
                with ui.row().classes("items-center"):
                    ui.icon("warning").classes("text-2xl")
                    ui.label(_("Empty Here.")).classes("font-bold")

            with self.browser_table.add_slot("top-left"):
                with ui.row().classes("items-center gap-x-0"):
                    # 返回上一级目录按钮
                    ui.button(icon="arrow_upward", on_click=self.back_func).props(
                        "flat dense"
                    ).tooltip(_("Back to Parent Directory"))

                    # 路径分隔符
                    if self.current_path.parts:
                        home_button = ui.button(
                            text=_("Home"),
                            on_click=lambda: self.goto_func(Path(initial_path)),
                        ).props("flat dense")
                        home_button.tooltip(_("Back to Home Directory"))

                        ui.icon("chevron_right").classes("text-xl text-gray-500 mx-0.5")

                    # 面包屑导航栏渲染，构建累积路径
                    MAX_DISPLAY_PARTS = 3
                    path_parts = [p for p in self.current_path.parts if p]
                    cumulative_path = Path()

                    for index, p in enumerate(path_parts):

                        if cumulative_path == Path(""):
                            cumulative_path = Path(p)
                        else:
                            cumulative_path /= p

                        target_path = cumulative_path

                        is_first = index == 0
                        is_second_last = index == len(path_parts) - 2
                        is_last = index == len(path_parts) - 1

                        should_display_button = (
                            len(path_parts) <= MAX_DISPLAY_PARTS
                            or is_first
                            or is_second_last
                            or is_last
                        )

                        if should_display_button:
                            # 跳转按钮本身
                            if not is_last:
                                ui.button(
                                    p,
                                    on_click=lambda path_to_go=target_path: self.goto_func(
                                        path_to_go
                                    ),
                                ).props(f"no-caps flat dense")
                                # 按钮后的分隔符
                                ui.icon("chevron_right").classes(
                                    "text-xl text-gray-500 mx-0.5"
                                )
                            else:
                                ui.button(p, on_click=self.copy_path_clipboard).props(
                                    "no-caps flat dense"
                                ).tooltip(str(self.current_path))

                        elif index == 1 and len(path_parts) > MAX_DISPLAY_PARTS:
                            ui.button("...").props("flat dense disable")
                            ui.icon("chevron_right").classes(
                                "text-xl text-gray-500 mx-0.5"
                            )

            with self.browser_table.add_slot("top-right"):
                with ui.row().classes("items-center gap-4"):
                    self.upload_button = (
                        ui.button(
                            icon="cloud_upload",
                            on_click=self.handle_upload_button_click,
                        )
                        .props("flat dense")
                        .tooltip(_("Upload"))
                    )
                    self.new_directory_button = (
                        ui.button(
                            icon="create_new_folder",
                            on_click=self.handle_new_directory_button_click,
                        )
                        .props("flat dense")
                        .tooltip(_("New Directory"))
                    )
                    self.delete_button = (
                        ui.button(
                            icon="delete_forever",
                            on_click=self.handle_delete_button_click,
                        )
                        .props("flat dense")
                        .tooltip(_("Delete"))
                    )
                    self.download_button = (
                        ui.button(
                            icon="cloud_download",
                            on_click=self.handle_download_button_click,
                        )
                        .props("flat dense")
                        .tooltip(_("Download"))
                    )
                    self.move_button = (
                        ui.button(
                            icon="drive_file_move",
                            on_click=self.handle_move_button_click,
                        )
                        .props("flat dense")
                        .tooltip(_("Move"))
                    )

                    self.edit_button = (
                        ui.button(
                            icon=(
                                self.edit_button_icon_close
                                if self.is_select_mode
                                else self.edit_button_icon_open
                            ),
                            on_click=self.handle_edit_button_click,
                        )
                        .props("flat dense")
                        .tooltip(_("Batch Actions"))
                    )
                    self.search_button = (
                        ui.button(
                            icon="find_in_page",
                            on_click=self.handle_search_button_click,
                        )
                        .props("dense flat")
                        .tooltip(_("Search in Current Directory (./)"))
                    )

                    self.new_directory_button.set_visibility(not self.is_select_mode)
                    self.upload_button.set_visibility(not self.is_select_mode)
                    self.delete_button.set_visibility(self.is_select_mode)
                    self.move_button.set_visibility(self.is_select_mode)
                    self.download_button.set_visibility(self.is_select_mode)

                    self.browser_table.set_selection(
                        "multiple" if self.is_select_mode else None
                    )

            self.browser_table.add_slot(
                "body-cell-action",
                f"""
                <q-td :props="props">
                    <q-btn icon="info" @click="() => $parent.$emit('info', props.row)" flat dense><q-tooltip>{_("Information")}</<q-tooltip></q-btn>
                </q-td>
            """,
            )

            self.browser_table.add_slot(
                "body-cell-name", '<q-td v-html="props.row.name"></q-td>'
            )

            self.browser_table.rows = [
                {
                    "name": f"{get_file_icon(p.type, p.extension)} <b>{p.name}</b>",
                    "raw_name": p.name,
                    "type": p.type,
                    "extension": p.extension if p.extension else "-",
                    "path": p.path,
                    "size": bytes_to_human_readable(p.size) if p.size else "-",
                    "raw_size": p.size if p.size else -1,
                    "created_at": (
                        timestamp_to_human_readable(p.created_at, self.user_timezone)
                    ),
                    "updated_at": (
                        timestamp_to_human_readable(
                            p.custom_updated_at, self.user_timezone
                        )
                    ),
                }
                for p in self.file_list
            ]

            self.browser_table.on("row-click", self.handle_row_click)
            self.browser_table.on("row-dblclick", self.handle_row_double_click)

            self.browser_table.on("info", self.handle_info_button_click)

            self.browser_table.update()

            if self.pending_display_metadata_path is not None:
                await self._open_metadata_by_path(self.pending_display_metadata_path)
                self.pending_display_metadata_path = None

            return self.browser_table

        self.refresh_func = browser_content

        ui.timer(0.1, self.refresh_func, once=True)

    @property
    def current_path(self) -> Path:
        return self._current_path

    @current_path.setter
    def current_path(self, new_path: Path):
        old_path = self._current_path

        if old_path != new_path:
            self._current_path = new_path
            set_user_last_path(new_path)

    async def refresh(self):
        await self.refresh_func.refresh()

    async def back_func(self):
        if self.current_path.parent == self.current_path:
            notify.warning(_("Already at the root directory. Cannot go back further."))
            return

        await self.goto_func(self.current_path.parent)

    async def goto_func(self, path: Path):
        self.current_path = path
        self.current_path = (
            self.current_path.resolve()
            if self.current_path.is_absolute()
            else self.current_path.resolve().relative_to(Path.cwd())
        )
        await self.refresh()
        return

    def copy_path_clipboard(self):
        copy_to_clipboard(
            str(self.current_path), message=_("Path copied to clipboard.")
        )

    def handle_row_click(self, e: events.GenericEventArguments):
        click_event_params, click_row, click_index = e.args

        # In select mode
        if self.is_select_mode:
            if click_row in self.browser_table.selected:
                self.browser_table.selected.remove(click_row)
            else:
                self.browser_table.selected.append(click_row)

    async def handle_row_double_click(self, e: events.GenericEventArguments):
        if self.is_select_mode:
            return

        click_event_params, click_row, click_index = e.args
        target_path = click_row["path"]
        file_name = click_row["raw_name"]

        if click_row["type"] == "dir":
            await self.goto_func(Path(target_path))
            return
        else:
            confirm = await ConfirmDialog(
                _("Confirm Download"),
                _(
                    "Are you sure you want to download **`{}`**? To **delete**, **move**, **rename** or **share** this file, please use the **Information** button(i) next to the file row."
                ).format(file_name),
            ).open()
            if confirm:
                download_url = await generate_download_url(
                    self.current_user,
                    target_path,
                    file_name,
                    FileType.FILE,
                    FileSource.DOWNLOAD,
                )
                if not download_url:
                    return
                ui.navigate.to(download_url)
        return

    async def handle_new_directory_button_click(self):
        new_directory_name = await InputDialog(
            _("New Directory"),
            message=_(
                "Please enter the name of the new directory.\n\n"
                "You can use `/` to create subfolders, e.g., `parent/child`."
            ),
            input_label=_("Directory Name"),
        ).open()

        if new_directory_name:
            check, error_message = validate_filename(
                new_directory_name, allow_subdirs=True
            )
            if not check:
                notify.error(error_message)
                return

            new_directory = self.current_path / new_directory_name
            if self.file_manager.exists(new_directory):
                notify.warning(
                    _(
                        "A directory with the same name already exists. Please choose another name."
                    )
                )
            else:
                try:
                    self.file_manager.create_directory(new_directory)
                except Exception as e:
                    notify.error(_("Failed to create new directory: {}").format(str(e)))
                    return
                notify.success(
                    _("New directory created successfully: {}").format(new_directory)
                )

        await self.refresh()

    async def handle_upload_button_click(self):
        self.on_upload = not self.on_upload
        if self.on_upload:
            self.upload_dialog.open()
        else:
            is_uploading = await self.upload_component.get_computed_prop("isUploading")
            if is_uploading:
                confirm = await ConfirmDialog(
                    _("Upload in Progress"),
                    _(
                        "Are you sure you want to cancel? This will stop the ongoing upload."
                    ),
                    warning=True,
                ).open()

                if confirm:
                    self.upload_dialog.close()
                else:
                    self.on_upload = not self.on_upload
            else:
                self.upload_dialog.close()

    async def handle_upload(self, e: events.MultiUploadEventArguments):
        for f in e.files:

            if self.file_manager.exists(str(self.current_path / f.name)):
                confirm = await ConfirmDialog(
                    _("File Exists: {}").format(f.name),
                    _("This file already exists. Do you want to overwrite it?"),
                    warning=True,
                ).open()
                if not confirm:
                    notify.warning(_("Cancel overwrite: {}").format(f.name))
                    continue

            try:
                await self.file_manager.upload_file(
                    f.iterate(), str(self.current_path / f.name)
                )
            except Exception as up_e:
                notify.error(up_e)

        self.upload_component.clear()

        await self.refresh()

    def handle_edit_button_click(self):
        self.is_select_mode = not self.is_select_mode

        if self.is_select_mode:
            notify.info(_("Multiple selection enabled"))

        self.browser_table.set_selection("multiple" if self.is_select_mode else None)
        self.browser_table.selected = []

        # 隐藏 action 列
        if self.is_select_mode:
            self.browser_table.columns.remove(self.action_column)
        else:
            self.browser_table.columns.append(self.action_column)

        self.new_directory_button.set_visibility(not self.is_select_mode)
        self.upload_button.set_visibility(not self.is_select_mode)
        self.move_button.set_visibility(self.is_select_mode)
        self.delete_button.set_visibility(self.is_select_mode)
        self.download_button.set_visibility(self.is_select_mode)
        self.edit_button.props(
            f"icon={self.edit_button_icon_close if self.is_select_mode else self.edit_button_icon_open}"
        )

    async def handle_download_button_click(self):
        if not self.browser_table.selected:
            notify.warning(_("Please select at least one file"))
            return

        confirm = await ConfirmDialog(
            _("Download Files"),
            _(
                "You selected multiple items or a folder. "
                "They will be compressed into a **single tar.gz file** for download. "
                "Do you want to continue?"
            ),
        ).open()

        if confirm:
            download_url = await generate_download_url(
                self.current_user,
                [s["path"] for s in self.browser_table.selected],
                [s["raw_name"] for s in self.browser_table.selected],
                FileType.MIXED,
                FileSource.DOWNLOAD,
            )
            if not download_url:
                return
            ui.navigate.to(download_url)
        return

    async def handle_move_button_click(self):
        if not self.browser_table.selected:
            notify.warning(_("Please select at least one file"))
            return

        confirm = await MoveDialog(
            self.file_manager,
            [f["raw_name"] for f in self.browser_table.selected],
            self.current_path,
        ).open()
        if confirm:
            # Checks if the target move directory is the same as the current directory.
            if confirm == self.current_path:
                notify.error(
                    _(
                        "Cannot move items to the same folder. Please select a different destination."
                    )
                )
                return

            result = []
            for item in self.browser_table.selected:
                try:
                    self.file_manager.move_file(
                        item["path"], confirm / item["raw_name"]
                    )
                    result.append({"action": "delete", "raw": item, "result": True})
                except Exception as e:
                    notify.error(e)
            notify.success(_("Moved {} items").format(len(result)))
        else:
            return

        await self.refresh()

    async def handle_delete_button_click(self):
        if not self.browser_table.selected:
            notify.warning(_("Please select at least one file"))
            return

        confirm = await ConfirmDialog(
            title=_("Delete {} items").format(len(self.browser_table.selected)),
            message=[
                f"{get_file_icon(item["type"], item["extension"])} {item["raw_name"]}"
                for item in self.browser_table.selected
            ],
            warning=True,
        ).open()

        if confirm:
            result = []
            try:
                for item in self.browser_table.selected:
                    if item["type"] == "dir":
                        self.file_manager.delete_directory(item["path"])
                    else:
                        self.file_manager.delete_file(item["path"])
                    result.append({"action": "delete", "raw": item, "result": True})
                notify.success(_("Deleted {} items").format(len(result)))
            except Exception as e:
                notify.error(e)
        else:
            return

        await self.refresh()

    async def handle_search_button_click(self):
        select_result = await SearchDialog(self.file_manager, self.current_path).open()

        if not select_result:
            return
        else:
            select_path = Path(select_result.path)

        if select_result.is_dir:
            self.current_path = select_path
        else:
            self.current_path = select_path.parent
            self.pending_display_metadata_path = str(select_path)

        await self.refresh()

    async def handle_info_button_click(
        self,
        e: events.GenericEventArguments,
    ):
        path = e.args.get("path")
        if not path:
            notify.error(_("Missing path"))
            return

        await self._open_metadata_by_path(path)

    async def _open_metadata_by_path(self, path: str):
        item_metadata = self.file_manager.get_file_metadata(path)

        if isinstance(item_metadata, (DirMetadata, FileMetadata)):
            await MetadataDialog(
                self.current_user,
                self.file_manager,
                item_metadata,
                self.current_path,
                self.refresh,
            ).open()
        else:
            notify.error(_("Failed to get file metadata"))
