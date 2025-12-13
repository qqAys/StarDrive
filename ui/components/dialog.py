from datetime import datetime, timezone, date, time

from nicegui import ui, events

from schemas.file_schema import FILE_NAME_FORBIDDEN_CHARS
from services.file_service import get_user_share_links, delete_download_link
from services.user_service import get_user_timezone
from ui.components.clipboard import copy_text_clipboard
from ui.components.notify import notify
from utils import _


class Dialog:
    dialog_props = 'backdrop-filter="blur(2px) brightness(90%)"'

    def __init__(self):
        self.dialog = ui.dialog().props(self.dialog_props)

    async def open(self):
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
            ui.label(self.title).classes("text-lg font-bold")
            if self.message:
                if isinstance(self.message, str):
                    ui.label(self.message)
                elif isinstance(self.message, list):
                    for message in self.message:
                        ui.label(message)

            with ui.row().classes("w-full justify-between"):
                ui.button(
                    _("Confirm"),
                    on_click=lambda: self.dialog.submit(True),
                    color="red" if self.warning else "green",
                )
                ui.button(_("Cancel"), on_click=lambda: self.dialog.submit(False))

        r = await self.dialog
        return r


class RenameDialog(Dialog):
    def __init__(self, title: str, old_name: str):
        super().__init__()
        self.title = title
        self.old_name = old_name

        self.dialog = ui.dialog().props(self.dialog_props)

    async def open(self):
        with self.dialog, ui.card().classes("w-full"):
            ui.label(self.title).classes("text-lg font-bold")
            new_name = ui.input(label=_("New name"), value=self.old_name).classes(
                "w-full"
            )

            def is_same(a, b):
                return a == b

            def on_confirm():
                if not new_name.value.strip():
                    notify.warning(_("New name cannot be empty"))
                    return None
                if is_same(new_name.value, self.old_name):
                    notify.warning(_("New name cannot be the same as the old name"))
                    return None
                if any(char in new_name.value for char in FILE_NAME_FORBIDDEN_CHARS):
                    notify.warning(
                        f"File name cannot contain any of the following characters: {FILE_NAME_FORBIDDEN_CHARS}"
                    )
                    return None
                if new_name.value.endswith("."):
                    notify.warning(_("File name cannot end with a dot"))
                    return None

                return self.dialog.submit(new_name.value.strip())

            with ui.row().classes("w-full justify-between"):
                ui.button(
                    _("Confirm"),
                    on_click=on_confirm,
                    color="green",
                )
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
            ui.label(self.title).classes("text-lg font-bold")

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
                            )
                            .props("no-caps dense")
                            .classes("md:w-auto w-full") as dropdown_button
                        ):
                            with ui.row(wrap=False).classes("w-full justify-between"):
                                ui.button(
                                    _("Copy"),
                                    icon="content_copy",
                                    on_click=lambda: copy_text_clipboard(link_url),
                                ).classes("w-full").props("flat dense")
                                ui.button(
                                    _("Delete"),
                                    icon="delete",
                                    on_click=lambda: delete_share_link(
                                        share_link["id"]
                                    ),
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
