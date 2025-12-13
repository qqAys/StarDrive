from pathlib import Path
from typing import Optional

from nicegui import ui, events
from starlette.formparsers import MultiPartParser

from services.file_service import StorageManager, get_file_icon, generate_download_url
from ui.components import max_w
from ui.components.dialog import ConfirmDialog, RenameDialog
from ui.components.input import input_with_icon
from ui.components.notify import notify
from utils import _, bytes_to_human_readable, timestamp_to_human_readable

size_sort_js = """(a, b, rowA, rowB) => {
    const isDirA = rowA.type === 'dir';
    const isDirB = rowB.type === 'dir';

    // 目录优先
    if (isDirA && !isDirB) return -1;
    if (!isDirA && isDirB) return 1;

    // 按 raw_size 排序
    return rowA.raw_size - rowB.raw_size;
}"""


MultiPartParser.spool_max_size = 1024 * 1024 * 5  # 5 MB


class FileBrowserTable:
    def __init__(
        self,
        file_service: StorageManager,
        initial_path: str = ".",
        target_path: str = "",
        upload_component: ui.upload = None,
        upload_dialog: ui.dialog = None,
    ):

        self.file_service = file_service

        self.browser_table: Optional[ui.table] = None
        self.action_column = {
            "sortable": False,
            "name": "action",
            "label": _("Action"),
            "style": "width: 0px",
            "align": "center",
        }

        self.is_select_mode = False
        self.edit_button_icon_open = "keyboard_arrow_left"
        self.edit_button_icon_close = "keyboard_arrow_right"
        self.search_input: Optional[ui.input] = None
        self.edit_button: Optional[ui.button] = None
        self.delete_button: Optional[ui.button] = None
        self.move_button: Optional[ui.button] = None
        self.upload_button: Optional[ui.button] = None
        self.download_button: Optional[ui.button] = None

        self.upload_component = upload_component
        self.upload_component.on_multi_upload(self.handle_upload)
        self.upload_dialog = upload_dialog
        self.on_upload = False

        self.file_list = []

        self.current_path: Path = Path(initial_path, target_path)

        if not self.file_service.exists(str(self.current_path)):
            notify.error(_("Path not exists, will go to home dir."))
            self.current_path: Path = Path(initial_path)

        @ui.refreshable
        async def browser_content():
            self.file_list = self.file_service.list_files(str(self.current_path))

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
            ).classes("w-full h-full" + max_w)

            self.browser_table.pagination = {
                "sortBy": "type",
                "descending": False,
                "page": 1,
                "rowsPerPage": 0 if len(self.file_list) < 50 else 15,
            }

            with self.browser_table.add_slot("no-data"):
                with ui.row().classes("items-center"):
                    ui.icon("warning").classes("text-2xl")
                    ui.label(_("Empty here.")).classes("font-bold")

            with self.browser_table.add_slot("top-left"):
                with ui.row().classes("items-center gap-x-0"):
                    # 返回上一级目录按钮
                    ui.button(icon="arrow_upward", on_click=self.back_func).props(
                        "flat dense"
                    ).tooltip(_("Back to parent directory"))

                    # 路径分隔符
                    if self.current_path.parts:
                        home_button = ui.button(
                            text=_("Home"),
                            on_click=lambda: self.goto_func(Path(initial_path)),
                        ).props("flat dense")
                        home_button.tooltip(_("Back to home directory"))

                        ui.icon("chevron_right").classes("text-xl text-gray-500 mx-0.5")

                    # 面包屑导航栏渲染，构建累积路径
                    MAX_DISPLAY_PARTS = 3
                    path_parts = [p for p in self.current_path.parts if p]
                    cumulative_path = Path()

                    for index, p in enumerate(path_parts):

                        if cumulative_path == Path("."):
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
                                ).tooltip("/" + str(self.current_path))

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
                    self.download_button = (
                        ui.button(
                            icon="cloud_download", on_click=self.handle_move_button_click
                        )
                        .props("flat dense")
                        .tooltip(_("Download"))
                    )
                    self.move_button = (
                        ui.button(
                            icon="drive_file_move", on_click=self.handle_move_button_click
                        )
                        .props("flat dense")
                        .tooltip(_("Move"))
                    )
                    self.delete_button = (
                        ui.button(
                            icon="delete",
                            on_click=self.handle_delete_button_click,
                        )
                        .props("flat dense")
                        .tooltip(_("Delete"))
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
                        .tooltip(_("More actions"))
                    )
                    self.search_input = (
                        input_with_icon(_("Search"), icon="search")
                        .bind_value(self.browser_table, "filter")
                        .props("clearable dense")
                    )

                    self.upload_button.set_visibility(not self.is_select_mode)
                    self.download_button.set_visibility(self.is_select_mode)
                    self.move_button.set_visibility(self.is_select_mode)
                    self.delete_button.set_visibility(self.is_select_mode)
                    self.browser_table.set_selection(
                        "multiple" if self.is_select_mode else None
                    )

            self.browser_table.add_slot(
                "body-cell-action",
                f"""
                <q-td :props="props">
                    <q-btn icon="share" @click="() => $parent.$emit('share', props.row)" flat dense><q-tooltip>{_("Share")}</<q-tooltip></q-btn>
                    <q-btn icon="drive_file_rename_outline" @click="() => $parent.$emit('rename', props.row)" flat dense><q-tooltip>{_("Rename")}</<q-tooltip></q-btn>
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
                    "extension": p.extension,
                    "path": p.path,
                    "size": bytes_to_human_readable(p.size) if p.size else "-",
                    "raw_size": p.size if p.size else -1,
                    "created_at": (
                        timestamp_to_human_readable(p.created_at)
                        if p.created_at
                        else "-"
                    ),
                    "updated_at": (
                        timestamp_to_human_readable(p.updated_at)
                        if p.updated_at
                        else "-"
                    ),
                }
                for p in self.file_list
            ]

            self.browser_table.on("row-click", self.handle_row_click)
            self.browser_table.on("row-dblclick", self.handle_row_double_click)

            self.browser_table.on("rename", self.handle_rename_button_click)
            self.browser_table.on("share", self.handle_share_button_click)

            self.browser_table.update()

            return self.browser_table

        self.refresh_func = browser_content

        ui.timer(0.1, self.refresh_func, once=True)

    async def refresh(self):
        await self.refresh_func.refresh()

    async def back_func(self):
        if self.current_path.parent == self.current_path:
            notify.warning(_("You are already at the root directory"))
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
        ui.clipboard.write(str(self.current_path))
        notify.success(_("Path copied to clipboard"))

    def handle_row_click(self, e: events.GenericEventArguments):
        click_event_params, click_row, click_index = e.args

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
            download_url = generate_download_url(target_path, file_name)
            ui.navigate.to(download_url)
            return

    async def handle_upload_button_click(self):
        self.on_upload = not self.on_upload
        if self.on_upload:
            self.upload_dialog.open()
        else:
            is_uploading = await self.upload_component.get_computed_prop("isUploading")
            if is_uploading:
                confirm = await ConfirmDialog(
                    _("Upload is still in progress"),
                    _(
                        "Are you sure you want to cancel the upload? This will cancel the upload process"
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

            if self.file_service.exists(str(self.current_path / f.name)):
                confirm = await ConfirmDialog(
                    _("File already exists: {}").format(f.name),
                    _("Do you want to overwrite it?"),
                    warning=True,
                ).open()
                if not confirm:
                    notify.warning(_("Cancel overwrite: {}").format(f.name))
                    continue

            try:
                await self.file_service.upload_file(
                    f.iterate(), str(self.current_path / f.name)
                )
            except Exception as up_e:
                notify.error(up_e)

        self.upload_component.clear()

        await self.refresh()

    def handle_edit_button_click(self):
        self.is_select_mode = not self.is_select_mode

        if self.is_select_mode:
            notify.info(_("Select mode enabled"))

        self.browser_table.set_selection("multiple" if self.is_select_mode else None)
        self.browser_table.selected = []

        # 隐藏 action 列
        if self.is_select_mode:
            self.browser_table.columns.remove(self.action_column)
        else:
            self.browser_table.columns.append(self.action_column)

        self.edit_button.props(
            f"icon={self.edit_button_icon_close if self.is_select_mode else self.edit_button_icon_open}"
        )
        self.upload_button.set_visibility(not self.is_select_mode)
        self.download_button.set_visibility(self.is_select_mode)
        self.move_button.set_visibility(self.is_select_mode)
        self.delete_button.set_visibility(self.is_select_mode)

    async def handle_move_button_click(self):
        if not self.browser_table.selected:
            notify.warning(_("Please select at least one file"))
            return
        raise NotImplementedError

    async def handle_rename_button_click(self, e: events.GenericEventArguments):
        target_path = e.args["path"]
        file_name = e.args["raw_name"]
        new_name = await RenameDialog(
            title=_("Rename: {}".format(file_name)), old_name=file_name
        ).open()
        if new_name:
            new_path = Path(target_path).parent / new_name
            if self.file_service.exists(new_path):
                notify.warning(
                    _("File or directory already exists, please choose another name")
                )
                return
            try:
                self.file_service.move_file(target_path, new_path)
                notify.success(_("Rename successful"))
            except Exception as e:
                notify.error(e)
        else:
            return

        await self.refresh()

    async def handle_delete_button_click(self):
        if not self.browser_table.selected:
            notify.warning(_("Please select at least one file"))
            return

        confirm = await ConfirmDialog(
            title=_("Are you sure you want to delete {} items?").format(
                len(self.browser_table.selected)
            ),
            message=[item["raw_name"] for item in self.browser_table.selected],
            warning=True,
        ).open()

        if confirm:
            result = []
            try:
                for item in self.browser_table.selected:
                    if item["type"] == "dir":
                        self.file_service.delete_directory(item["path"])
                    else:
                        self.file_service.delete_file(item["path"])
                    result.append({"action": "delete", "raw": item, "result": True})
                notify.success(_("Deleted {} items").format(len(result)))
            except Exception as e:
                notify.error(e)
        else:
            return

        await self.refresh()

    @staticmethod
    async def handle_share_button_click(e: events.GenericEventArguments):
        target_path = e.args["path"]
        file_name = e.args["raw_name"]
        confirm = await ConfirmDialog(title=_("Share {}?").format(target_path)).open()
        if confirm:
            download_url = generate_download_url(target_path, file_name)
            ui.clipboard.write(download_url)
            notify.success(_("Copied share link to clipboard {}").format(target_path))
