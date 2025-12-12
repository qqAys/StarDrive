from pathlib import Path
from typing import Optional

from nicegui import ui, events

from services.file_service import StorageManager
from ui.components.dialog import AskDialog
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
    ):

        self.file_service = file_service

        self.browser_table: Optional[ui.table] = None

        self.is_select_mode = False
        self.edit_button_icon_open = "keyboard_arrow_left"
        self.edit_button_icon_close = "keyboard_arrow_right"
        self.search_input: Optional[ui.input] = None
        self.edit_button: Optional[ui.button] = None
        self.remove_button: Optional[ui.button] = None

        self.file_list = []

        self.current_path: Path = Path(initial_path)

        @ui.refreshable
        async def browser_content():
            self.file_list = self.file_service.list_files(self.current_path.__str__())
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
                    "name": "size",
                    "label": _("Size"),
                    "field": "size",
                    "align": "right",
                    "required": True,
                    ":sort": size_sort_js,
                },
                {
                    "name": "created_at",
                    "label": _("Created At"),
                    "field": "created_at",
                },
                {
                    "name": "updated_at",
                    "label": _("Updated At"),
                    "field": "updated_at",
                },
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
                    "headerClasses": "text-primary",
                },
            ).classes("w-full h-full")

            self.browser_table.pagination = {
                "sortBy": "type",
                "descending": False,
                "page": 1,
                "rowsPerPage": 0 if len(self.file_list) < 50 else 15,
            }

            with self.browser_table.add_slot("top-left"):
                with ui.row().classes("items-center gap-x-0"):
                    # 返回上一级目录按钮
                    ui.button(icon="arrow_upward", on_click=self.back_func).props(
                        "flat dense"
                    )

                    # 路径分隔符
                    if self.current_path.parts:
                        home_button = ui.button(
                            text=_("Home"),
                            on_click=lambda: self.goto_func(Path(initial_path)),
                        ).props("flat dense")
                        home_button.tooltip(self.current_path.__str__())

                        ui.icon("chevron_right").classes(
                            "text-xl text-gray-500 mx-0.5 cursor-pointer"
                        )

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
                            ui.button(
                                p,
                                on_click=lambda path_to_go=target_path: self.goto_func(
                                    path_to_go
                                ),
                            ).props(f"flat dense{" disable" if is_last else ""}")
                            # 按钮后的分隔符
                            if not is_last:
                                ui.icon("chevron_right").classes(
                                    "text-xl text-gray-500 mx-0.5"
                                )

                        elif index == 1 and len(path_parts) > MAX_DISPLAY_PARTS:
                            ui.button("...").props("flat dense disable")
                            ui.icon("chevron_right").classes(
                                "text-xl text-gray-500 mx-0.5"
                            )

            with self.browser_table.add_slot("top-right"):
                with ui.row().classes("items-center gap-4"):
                    self.remove_button = ui.button(
                        icon="delete", on_click=self.handle_remove_button_click
                    ).props("flat dense")
                    self.edit_button = ui.button(
                        icon=(
                            self.edit_button_icon_close
                            if self.is_select_mode
                            else self.edit_button_icon_open
                        ),
                        on_click=self.handle_edit_button_click,
                    ).props("flat dense")
                    self.search_input = (
                        input_with_icon(_("Search"), icon="search")
                        .bind_value(self.browser_table, "filter")
                        .props("clearable dense")
                    )

                    self.remove_button.set_visibility(self.is_select_mode)
                    self.browser_table.set_selection(
                        "multiple" if self.is_select_mode else None
                    )

            self.browser_table.add_slot(
                "body-cell-name", '<q-td v-html="props.row.name"></q-td>'
            )

            self.browser_table.rows = [
                {
                    "name": f"📁 <b>{p.name}</b>" if p.type == "dir" else p.name,
                    "raw_name": p.name,
                    "type": p.type,
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

            self.browser_table.update()

            return self.browser_table

        self.refresh_func = browser_content

        ui.timer(0.1, self.refresh_func, once=True)

    async def refresh(self):
        await self.refresh_func.refresh()

    async def back_func(self):
        if self.current_path.parent == self.current_path:
            notify.warning(_("You are already at the root directory."))
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

    def copy_path_to_clipboard(self):
        try:
            ui.clipboard.write(self.current_path.__str__())
        except Exception as e:
            notify.error(_("Failed to copy path to clipboard."))

        notify.success(_("Copied to clipboard."))

    async def handle_row_click(self, e: events.GenericEventArguments):
        click_event_params, click_row, click_index = e.args

        if self.is_select_mode:
            if click_row in self.browser_table.selected:
                self.browser_table.selected.remove(click_row)
            else:
                self.browser_table.selected.append(click_row)
            return

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

        self.browser_table.set_selection("multiple" if self.is_select_mode else None)
        self.browser_table.selected = []
        self.edit_button.props(
            f"icon={self.edit_button_icon_close if self.is_select_mode else self.edit_button_icon_open}"
        )
        self.remove_button.set_visibility(self.is_select_mode)

    async def handle_remove_button_click(self):
        if not self.browser_table.selected:
            notify.warning(_("Please select at least one file!"))
            return

        confirm = await AskDialog(
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
                notify.success(_("Deleted {} items.").format(len(result)))
            except Exception as e:
                notify.error(e)
        else:
            return

        await self.refresh()
