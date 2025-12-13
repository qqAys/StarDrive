from pathlib import Path
from typing import Optional

from nicegui import ui, events

from services.file_service import StorageManager, get_file_icon
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


class FileBrowserTable:
    def __init__(
        self,
        file_service: StorageManager,
        initial_path: str = ".",
        target_path: str = "",
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
                    "classes": "hidden",
                    "headerClasses": "hidden",
                },
                {
                    "name": "size",
                    "label": _("Size"),
                    "field": "size",
                    "required": True,
                    ":sort": size_sort_js,
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
                                ).props(
                                    f"no-caps flat dense"
                                )
                                # 按钮后的分隔符
                                ui.icon("chevron_right").classes(
                                    "text-xl text-gray-500 mx-0.5"
                                )
                            else:
                                ui.button(p, on_click=self.copy_path_clipboard).props("no-caps flat dense").tooltip("/" + str(self.current_path))

                        elif index == 1 and len(path_parts) > MAX_DISPLAY_PARTS:
                            ui.button("...").props("flat dense disable")
                            ui.icon("chevron_right").classes(
                                "text-xl text-gray-500 mx-0.5"
                            )

            with self.browser_table.add_slot("top-right"):
                with ui.row().classes("items-center gap-4"):
                    self.move_button = (
                        ui.button(
                            icon="move_to_inbox", on_click=self.handle_move_button_click
                        )
                        .props("flat dense")
                        .tooltip(_("Move"))
                    )
                    self.delete_button = (
                        ui.button(
                            icon="delete_outline",
                            on_click=self.handle_delete_button_click,
                        )
                        .props("flat dense")
                        .tooltip(_("Delete"))
                    )
                    self.edit_button = ui.button(
                        icon=(
                            self.edit_button_icon_close
                            if self.is_select_mode
                            else self.edit_button_icon_open
                        ),
                        on_click=self.handle_edit_button_click,
                    ).props("flat dense").tooltip(_("More actions"))
                    self.search_input = (
                        input_with_icon(_("Search"), icon="search")
                        .bind_value(self.browser_table, "filter")
                        .props("clearable dense")
                    )

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
        notify.success(_("Copied to clipboard"))

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

        if click_row["type"] == "dir":
            await self.goto_func(Path(target_path))
            return
        else:
            ui.download.content(
                self.file_service.download_file(target_path), click_row["name"]
            )

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
        self.move_button.set_visibility(self.is_select_mode)
        self.delete_button.set_visibility(self.is_select_mode)

    async def handle_move_button_click(self):
        if not self.browser_table.selected:
            notify.warning(_("Please select at least one file"))
            return
        raise NotImplementedError

    async def handle_rename_button_click(self, e: events.GenericEventArguments):
        target_path = e.args["path"]
        new_name = await RenameDialog(
            title=_("Rename"), old_name=e.args["raw_name"]
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
        confirm = await ConfirmDialog(title=_("Share {}?").format(target_path)).open()
        if confirm:
            # share_link = self.file_service.share_file(target_path)
            # ui.clipboard.write(share_link)
            notify.success(_("Copied share link to clipboard {}").format(target_path))
