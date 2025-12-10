from typing import Callable

from nicegui import ui

from ui.components.dialog import AskDialog
from utils import _


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
