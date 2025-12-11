from pathlib import Path
from typing import Callable

from nicegui import ui, events

from services.file_service import StorageManager
from ui.components.dialog import AskDialog
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

        self.file_list = []

        self.current_path = initial_path

        @ui.refreshable
        async def browser_content():
            self.file_list = self.file_service.list_files(self.current_path)
            columns = [
                {
                    "name": "name",
                    "label": _("Name"),
                    "field": "name",
                    "align": "left",
                    "required": True,
                    "sortable": True,
                },
                {
                    "name": "size",
                    "label": _("Size"),
                    "field": "size",
                    "align": "right",
                    "required": True,
                    "sortable": True,
                    ":sort": size_sort_js,
                },
                {
                    "name": "created_at",
                    "label": _("Created At"),
                    "field": "created_at",
                    "sortable": True,
                },
                {
                    "name": "updated_at",
                    "label": _("Updated At"),
                    "field": "updated_at",
                    "sortable": True,
                },
                {
                    "name": "action",
                    "label": _("Action"),
                    "align": "center",
                },
            ]
            browser_table = ui.table(
                columns=columns,
                rows=[],
                row_key="file",
                title=_("File List"),
                pagination=0,
                column_defaults={"align": "left"},
            ).classes("w-full h-full")

            browser_table.pagination = {
                "sortBy": None,
                "descending": False,
                "page": 1,
                "rowsPerPage": 0 if len(self.file_list) < 50 else 15,
            }

            add_table_controls(
                browser_table, show_path=self.current_path, back_func=self.back_func
            )

            browser_table.add_slot(
                "body-cell-name", '<q-td v-html="props.row.name"></q-td>'
            )
            browser_table.add_slot(
                "body-cell-action",
                f"""
                <q-td :props="props">
                    <q-btn flat dense round icon="share" @click="() => $parent.$emit('share', props.row)" />
                    <q-btn flat dense round icon="delete" @click="() => $parent.$emit('delete', props.row)" />
                    <q-btn flat dense round icon="download" @click="() => $parent.$emit('download', props.row)" />
                    <q-btn flat dense round icon="edit_document" @click="() => $parent.$emit('rename', props.row)" />
                    <q-btn flat dense round icon="drive_file_move" @click="() => $parent.$emit('move', props.row)" />
                </q-td>
            """,
            )

            browser_table.rows = [
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

            browser_table.on("row-dblclick", self.handle_row_double_click)
            browser_table.on("delete", lambda e: self.handle_action_click("delete", e))

            return browser_table

        self.refresh_func = browser_content

        ui.timer(0.1, self.refresh_func, once=True)

    async def refresh(self):
        await self.refresh_func.refresh()

    async def back_func(self):
        if self.current_path == ".":
            notify.warning(_("You are already at the root directory"))
            return
        self.current_path = Path(self.current_path).parent.__str__()
        await self.refresh()

    async def handle_row_double_click(self, e: events.GenericEventArguments):
        click_event_params, click_row, click_index = e.args
        target_path = click_row["path"]

        if click_row["type"] == "dir":
            self.current_path = target_path
            await self.refresh()
        else:
            ui.download.content(
                self.file_service.download_file(target_path), click_row["name"]
            )

    async def handle_action_click(self, action, e: events.GenericEventArguments):
        click_row = e.args

        click_name = click_row["raw_name"]
        click_path = click_row["path"]
        click_type = click_row["type"]

        if action == "delete":
            confirm = await AskDialog(
                title=(
                    _("Delete file") if click_type == "file" else _("Delete folder")
                ),
                message=_("Are you sure you want to delete {}?").format(click_name),
                warning=True,
            ).open()
            if confirm:
                try:
                    if click_type == "dir":
                        self.file_service.delete_directory(click_path)
                    else:
                        self.file_service.delete_file(click_path)
                    notify.success(_("Successfully deleted {}").format(click_name))
                except Exception as e:
                    notify.error(e)
            else:
                return

        await self.refresh()


def add_table_controls(
    table: ui.table,
    dialog_pass_func: Callable = lambda _: None,
    add_remove_controls: bool = False,
    remove_all: bool = False,
    show_path: str = ".",
    back_func: Callable = lambda _: None,
):
    with table.add_slot("top-left"):
        with ui.row().classes("items-center gap-4"):
            ui.button(icon="arrow_back", on_click=back_func).props("flat")
            ui.label(show_path)

    with table.add_slot("top-right"):
        with ui.row().classes("items-center gap-4"):
            ui.input(_("filter")).bind_value(table, "filter").props("clearable dense")

            if add_remove_controls:

                async def handle_remove_click(_remove_all: bool = False):
                    if _remove_all:
                        table_selected = table.rows
                    else:
                        table_selected = table.selected
                        if not table_selected:
                            return
                    confirm = await AskDialog(
                        _("You are going to remove {} records, are you sure?").format(
                            len(table_selected)
                        ),
                    ).open()
                    if confirm:
                        dialog_pass_func(table_selected)

                def handle_edit_click():
                    table.set_selection("multiple" if table.selection is None else None)
                    table.selected = []
                    edit_button.props(
                        "icon=playlist_add_check"
                        if remove_button.visible is False
                        else "icon=edit_note"
                    )
                    edit_button.text = (
                        _("Done") if remove_button.visible is False else _("Edit")
                    )
                    remove_button.set_enabled(remove_button.visible is True)
                    remove_button.set_visibility(remove_button.visible is False)
                    remove_all_button.set_visibility(remove_all_button.visible is False)

                remove_button = ui.button(
                    _("Remove selected"), icon="remove", on_click=handle_remove_click
                ).props("flat")
                remove_button.set_visibility(False)

                if remove_all:
                    remove_all_button = ui.button(
                        _("Remove all"),
                        icon="clear_all",
                        on_click=lambda: handle_remove_click(_remove_all=True),
                    ).props("flat")
                    remove_all_button.set_visibility(False)

                edit_button = ui.button(
                    _("Edit"), icon="edit_note", on_click=handle_edit_click
                ).props("flat")

                def toggle_remove_button(e):
                    if not e.selection:
                        remove_button.set_enabled(False)
                    else:
                        remove_button.set_enabled(True)

                table.on_select(toggle_remove_button)

                remove_button.set_enabled(False)
