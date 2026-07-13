import gc
import os

import psutil
from fastapi.requests import Request
from nicegui import APIRouter, Client, app, ui
from starlette.responses import RedirectResponse

from app.config import settings
from app.core.i18n import _
from app.core.paths import STORAGE_DIR
from app.security.guards import require_user
from app import globals
from app.services.file_service import get_user_storage_usage
from app.services.storage_config_service import (
    ALIYUN_OSS,
    LOCAL_STORAGE,
    StorageProfileDraft,
    storage_config,
)
from app.services.theme_service import (
    CUSTOM_THEME_ID,
    THEME_PRESETS,
    ThemeConfig,
    theme_config,
)
from app.ui.components.base import BaseLayout
from app.ui.components.dialog import ConfirmDialog
from app.ui.components.json_edit import style
from app.ui.components.notify import notify
from app.ui.theme import theme
from app.utils.size import bytes_to_human_readable

this_page_routes = "/console"


@app.get(this_page_routes)
def browser_index():
    """Redirect the console base route to its index page."""
    return RedirectResponse(f"{this_page_routes}/")


router = APIRouter(prefix=this_page_routes)


def get_process_memory() -> int:
    """Return the current memory usage (in bytes) of the application process."""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss


def get_system_metrics():
    """Collect key system and application performance metrics."""
    memory_info = psutil.virtual_memory()
    disk_usage = psutil.disk_usage("/")
    return {
        "cpu": psutil.cpu_percent(interval=None),
        "memory_percent": memory_info.percent,
        "memory_total": round(memory_info.total / (1024**3), 2),
        "memory_used": round(memory_info.used / (1024**3), 2),
        "process_memory": round(get_process_memory() / (1024**2), 2),
        "disk_percent": disk_usage.percent,
        "system_load": psutil.getloadavg(),
    }


def _format_time(value) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else "-"


def _readable_text_color(background_color: str) -> str:
    color = background_color.lstrip("#")
    if len(color) != 6:
        return "white"
    red, green, blue = (
        int(color[0:2], 16),
        int(color[2:4], 16),
        int(color[4:6], 16),
    )
    brightness = (red * 299 + green * 587 + blue * 114) / 1000
    return "black" if brightness > 160 else "white"


def _build_storage_profile_table_row(profile) -> dict:
    return {
        "id": profile.id,
        "name": profile.name,
        "backend": profile.backend_type,
        "backend_type": profile.backend_type,
        "active": _("Yes") if profile.is_active else _("No"),
        "is_active": profile.is_active,
        "has_secrets": profile.has_secrets,
        "secrets": _("Yes") if profile.has_secrets else _("No"),
        "tested": _format_time(profile.last_tested_at),
        "result": (
            "-"
            if profile.last_test_success is None
            else (_("Passed") if profile.last_test_success else _("Failed"))
        ),
        "last_test_success": profile.last_test_success,
        "last_test_message": profile.last_test_message or "-",
        "public_config": profile.public_config,
    }


def _replacement_storage_profile_row(rows: list[dict], deleted_profile_id: str):
    candidates = [row for row in rows if row["id"] != deleted_profile_id]
    local = next(
        (row for row in candidates if row["backend_type"] == LOCAL_STORAGE),
        None,
    )
    return local or (candidates[0] if candidates else None)


def _build_user_table_row(user, usage: int) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "active": _("Yes") if user.is_active else _("No"),
        "is_active": user.is_active,
        "admin": _("Yes") if user.is_superuser else _("No"),
        "is_superuser": user.is_superuser,
        "quota_bytes": user.quota_bytes,
        "quota": (
            _("Unlimited")
            if not user.quota_bytes
            else bytes_to_human_readable(user.quota_bytes)
        ),
        "usage": bytes_to_human_readable(usage),
        "deleted": _format_time(user.deleted_at),
        "is_deleted": user.deleted_at is not None,
        "created_at": _format_time(user.created_at),
    }


def _modifiable_user_rows(rows: list[dict]) -> list[dict]:
    return [row for row in rows if not row.get("is_deleted")]


@router.page("/")
@require_user(superuser=True)
async def console_page(request: Request, client: Client):
    """Render the admin settings console."""
    async with BaseLayout().render(
        header=True,
        footer=True,
        args={"title": _("Console")},
    ):
        user_manager = globals.get_user_manager()

        with ui.row().classes("w-full min-h-[calc(100vh-160px)] gap-0"):
            with ui.column().classes(
                "w-56 shrink-0 border-r border-gray-200 pr-3 gap-1"
            ):
                ui.label(_("Console")).classes("text-xl font-bold mb-2")
                nav_buttons = {}
                for key, label, icon in [
                    ("overview", _("Overview"), "dashboard"),
                    ("appearance", _("Appearance"), "palette"),
                    ("storage", _("Storage backend"), "storage"),
                    ("users", _("User management"), "group"),
                    ("system", _("System status"), "monitor_heart"),
                    ("developer", _("Developer tools"), "terminal"),
                ]:
                    nav_buttons[key] = (
                        ui.button(label, icon=icon)
                        .props("flat no-caps align=left")
                        .classes("w-full justify-start")
                    )

            with ui.column().classes("flex-1 min-w-0 pl-6 gap-5"):
                sections = {
                    "overview": ui.column().classes("w-full gap-4"),
                    "appearance": ui.column().classes("w-full gap-4"),
                    "storage": ui.column().classes("w-full gap-4"),
                    "users": ui.column().classes("w-full gap-4"),
                    "system": ui.column().classes("w-full gap-4"),
                    "developer": ui.column().classes("w-full gap-4"),
                }

                def show_section(active_key: str):
                    for key, section in sections.items():
                        section.visible = key == active_key
                        section.update()
                        nav_buttons[key].props(
                            "flat no-caps align=left"
                            + (" color=primary" if key == active_key else "")
                        )
                        nav_buttons[key].update()

                for key, button in nav_buttons.items():
                    button.on("click", lambda _e, key=key: show_section(key))

                with sections["overview"]:
                    await _render_overview_section()

                with sections["appearance"]:
                    await _render_appearance_section()

                with sections["storage"]:
                    await _render_storage_section()

                with sections["users"]:
                    await _render_user_section(user_manager)

                system_timer = None
                with sections["system"]:
                    system_timer = _render_system_section()

                with sections["developer"]:
                    _render_developer_section()

                show_section("overview")

        if system_timer:

            @ui.context.client.on_delete
            def disconnect():
                system_timer.deactivate()
                system_timer.cancel()
                system_timer.delete()


async def _render_overview_section():
    ui.label(_("Overview")).classes("text-2xl font-bold")
    current = storage_config.current_profile
    with ui.grid(columns=3).classes("w-full gap-3"):
        _stat_card(_("Active storage"), current.name if current else LOCAL_STORAGE)
        _stat_card(_("Backend type"), storage_config.current_backend)
        _stat_card(_("Local root"), STORAGE_DIR.as_posix())

    ui.label(_("Service settings")).classes("text-lg font-bold mt-2")
    ui.input(_("Service URL")).bind_value(app.storage.general, "service_url").classes(
        "w-full max-w-2xl"
    )
    ui.label(
        _(
            "Storage switching changes which backend is displayed and used. It does not migrate or merge files."
        )
    ).classes("text-sm text-gray-500")


async def _render_appearance_section():
    ui.label(_("Appearance")).classes("text-2xl font-bold")
    ui.label(_("Choose the global color theme used by the application UI.")).classes(
        "text-sm text-gray-500"
    )

    current_config = theme_config.current_config
    current_palette = theme_config.palette_for(current_config)
    preset_options = {preset.id: _(preset.label) for preset in THEME_PRESETS.values()}
    preset_options[CUSTOM_THEME_ID] = _("Custom")

    preset_select = (
        ui.select(
            preset_options,
            value=current_config.preset_id,
            label=_("Theme"),
        )
        .props("dense")
        .classes("w-full max-w-sm")
    )

    custom_palette = {
        "primary": current_config.custom_palette.get(
            "primary", current_palette["primary"]
        ),
        "secondary": current_config.custom_palette.get(
            "secondary", current_palette["secondary"]
        ),
        "accent": current_config.custom_palette.get(
            "accent", current_palette["accent"]
        ),
    }

    def color_picker_button(label: str, field: str):
        with ui.column().classes("gap-1"):
            ui.label(label).classes("text-sm text-gray-500")
            button = (
                ui.button(icon="palette", color=custom_palette[field])
                .props(
                    f"unelevated text-color={_readable_text_color(custom_palette[field])}"
                )
                .classes("h-10 w-24")
            )
            with button:
                picker = ui.color_picker()
                picker.set_color(custom_palette[field])

            def update_color(e):
                custom_palette[field] = str(e.color).upper()
                button.set_background_color(custom_palette[field])
                button.props(
                    f"text-color={_readable_text_color(custom_palette[field])}"
                )

            picker.on_pick(update_color)

    with ui.grid(columns=3).classes("w-full max-w-3xl gap-3") as custom_fields:
        color_picker_button(_("Primary color"), "primary")
        color_picker_button(_("Secondary color"), "secondary")
        color_picker_button(_("Accent color"), "accent")

    ui.label(_("Current palette")).classes("text-lg font-bold mt-2")
    with ui.row().classes("w-full gap-3"):
        for label, color in [
            (_("Primary"), current_palette["primary"]),
            (_("Secondary"), current_palette["secondary"]),
            (_("Accent"), current_palette["accent"]),
            (_("Success"), current_palette["positive"]),
            (_("Warning"), current_palette["warning"]),
            (_("Error"), current_palette["negative"]),
            (_("Info"), current_palette["info"]),
        ]:
            with ui.column().classes("gap-1 items-center"):
                ui.element("div").classes(
                    "h-8 w-16 rounded border border-gray-200"
                ).style(f"background-color: {color}")
                ui.label(label).classes("text-xs text-gray-500")

    def update_custom_fields():
        custom_fields.visible = preset_select.value == CUSTOM_THEME_ID
        custom_fields.update()

    preset_select.on("update:model-value", lambda _e: update_custom_fields())

    async def save_theme():
        try:
            saved = await theme_config.save(
                ThemeConfig(
                    preset_id=str(preset_select.value or current_config.preset_id),
                    custom_palette=custom_palette,
                )
            )
        except ValueError as exc:
            notify.error(str(exc))
            return
        preset_select.value = saved.preset_id
        notify.success(_("Theme saved. Refresh the page to update all UI elements."))

    with ui.row().classes("gap-2"):
        ui.button(_("Save theme"), icon="save", on_click=save_theme)

    update_custom_fields()


async def _render_storage_section():
    ui.label(_("Storage backend")).classes("text-2xl font-bold")
    ui.label(
        _(
            "Manage backend profiles. Activating a profile switches the whole file browser view to that backend."
        )
    ).classes("text-sm text-gray-500")

    with ui.row().classes("w-full items-center gap-2"):
        ui.button(_("New profile"), icon="add", on_click=lambda: open_profile_editor())
        ui.button(_("Refresh"), icon="refresh", on_click=lambda: refresh_profiles())

    profile_table = ui.table(
        columns=[
            {"name": "name", "label": _("Name"), "field": "name", "align": "left"},
            {"name": "backend", "label": _("Backend"), "field": "backend"},
            {"name": "active", "label": _("Active"), "field": "active"},
            {"name": "secrets", "label": _("Secret"), "field": "secrets"},
            {"name": "tested", "label": _("Last Tested"), "field": "tested"},
            {"name": "result", "label": _("Test Result"), "field": "result"},
            {
                "name": "action",
                "label": _("Action"),
                "field": "action",
                "align": "center",
                "sortable": False,
                "style": "width: 0px",
            },
        ],
        rows=[],
        row_key="id",
        selection="single",
        pagination={"rowsPerPage": 8},
    ).classes("w-full")

    profile_table.add_slot(
        "body-cell-action",
        f"""
        <q-td :props="props">
            <q-btn icon="info" @click.stop="$parent.$emit('info', props.row)" class="text-primary" flat dense>
                <q-tooltip>{_("Show storage profile information")}</q-tooltip>
            </q-btn>
        </q-td>
    """,
    )

    async def refresh_profiles():
        profiles = await storage_config.list_profiles()
        profile_table.rows = [
            _build_storage_profile_table_row(profile) for profile in profiles
        ]
        profile_table.selected = []
        profile_table.update()

    async def open_profile_editor(row: dict | None = None):
        is_edit = row is not None
        public_config = dict(row["public_config"] or {}) if row else {}
        with ui.dialog() as editor_dialog, ui.card().classes("w-full max-w-3xl"):
            ui.label(
                _("Edit storage profile") if is_edit else _("New storage profile")
            ).classes("text-lg font-bold")

            profile_name = (
                ui.input(_("Profile name"), value=row["name"] if row else "")
                .props("dense")
                .classes("w-full")
            )
            backend_type = (
                ui.select(
                    {LOCAL_STORAGE: _("Local storage"), ALIYUN_OSS: _("Aliyun OSS")},
                    value=row["backend_type"] if row else ALIYUN_OSS,
                    label=_("Backend type"),
                )
                .props("dense")
                .classes("w-full")
            )
            if is_edit:
                backend_type.disable()

            with ui.column().classes("w-full gap-3") as local_form:
                ui.label(
                    _("Local storage is server-managed and read-only here.")
                ).classes("text-sm text-gray-500")
                ui.input(_("Local root path"), value=STORAGE_DIR.as_posix()).props(
                    "readonly dense"
                ).classes("w-full")

            with ui.column().classes("w-full gap-3") as oss_form:
                with ui.grid(columns=2).classes("w-full gap-3"):
                    oss_region = ui.input(
                        _("OSS region"), value=public_config.get("region", "")
                    ).props("dense")
                    oss_endpoint = ui.input(
                        _("OSS endpoint"), value=public_config.get("endpoint", "")
                    ).props("dense")
                    oss_bucket = ui.input(
                        _("OSS bucket"), value=public_config.get("bucket", "")
                    ).props("dense")
                    oss_access_key = ui.input(
                        _("AccessKey ID"),
                        value=public_config.get("access_key_id", ""),
                    ).props("dense")
                    oss_secret = ui.input(
                        _("AccessKey Secret"),
                        password=True,
                        password_toggle_button=True,
                    ).props(f"dense hint='{_('Leave empty to keep the saved secret')}'")
                    oss_prefix = ui.input(
                        _("Object prefix"), value=public_config.get("prefix", "")
                    ).props("dense")

            def update_backend_form():
                local_form.visible = backend_type.value == LOCAL_STORAGE
                oss_form.visible = backend_type.value == ALIYUN_OSS
                local_form.update()
                oss_form.update()

            def build_draft() -> StorageProfileDraft:
                secrets = {}
                if oss_secret.value:
                    secrets["access_key_secret"] = str(oss_secret.value).strip()
                return StorageProfileDraft(
                    profile_id=row["id"] if row else None,
                    name=str(profile_name.value or "").strip(),
                    backend_type=str(backend_type.value or LOCAL_STORAGE),
                    public_config={
                        "region": oss_region.value or "",
                        "endpoint": oss_endpoint.value or "",
                        "bucket": oss_bucket.value or "",
                        "access_key_id": oss_access_key.value or "",
                        "prefix": oss_prefix.value or "",
                    },
                    secrets=secrets,
                )

            async def test_draft():
                try:
                    result = await storage_config.test_profile(
                        draft_config=build_draft()
                    )
                except Exception as exc:
                    notify.error(str(exc))
                    return
                if result.success:
                    notify.success(result.message)
                else:
                    notify.error(result.message)

            async def save_profile():
                try:
                    await storage_config.create_or_update_profile(build_draft())
                except Exception as exc:
                    notify.error(str(exc))
                    return
                notify.success(_("Storage profile saved."))
                editor_dialog.submit(True)

            backend_type.on("update:model-value", lambda _e: update_backend_form())
            update_backend_form()

            with ui.row().classes("w-full justify-end gap-2"):
                ui.button(_("Cancel"), on_click=lambda: editor_dialog.submit(None))
                ui.button(_("Test draft"), icon="wifi_tethering", on_click=test_draft)
                ui.button(_("Save profile"), icon="save", on_click=save_profile)

        saved = await editor_dialog
        if saved:
            await refresh_profiles()

    async def test_profile(row: dict):
        result = await storage_config.test_profile(profile_id=row["id"])
        if result.success:
            notify.success(result.message)
        else:
            notify.error(result.message)
        await refresh_profiles()

    async def activate_profile(row: dict):
        if row["is_active"]:
            notify.info(_("This profile is already active."))
            return
        confirm = await ConfirmDialog(
            _("Activate storage profile"),
            _(
                "Switching storage changes the whole file browser view. Existing files are not migrated or merged. Continue?"
            ),
            warning=True,
        ).open()
        if not confirm:
            return
        try:
            await storage_config.activate_profile(row["id"])
        except Exception as exc:
            notify.error(str(exc))
            return
        notify.success(_("Storage profile activated."))
        await refresh_profiles()

    async def delete_profile(row: dict):
        replacement = _replacement_storage_profile_row(profile_table.rows, row["id"])
        if row["is_active"]:
            message = [
                _(
                    "Delete active storage profile **`{name}`**? Files are preserved, but the active backend will switch before deletion."
                ).format(name=row["name"]),
            ]
            if replacement:
                message.append(
                    _("Replacement profile: {name}").format(name=replacement["name"])
                )
        else:
            message = _(
                "Delete storage profile **`{name}`**? Files are preserved."
            ).format(name=row["name"])
        confirm = await ConfirmDialog(
            _("Delete storage profile"),
            message,
            warning=True,
        ).open()
        if not confirm:
            return
        try:
            await storage_config.delete_profile(row["id"])
        except Exception as exc:
            notify.error(str(exc))
            return
        notify.success(_("Storage profile deleted."))
        await refresh_profiles()

    async def open_profile_dialog(row: dict):
        with ui.dialog() as profile_dialog, ui.card().classes("w-full max-w-3xl"):
            with ui.row().classes("w-full justify-between items-center"):
                ui.label(_("Storage profile information")).classes("text-lg font-bold")
                ui.button(
                    icon="close", on_click=lambda: profile_dialog.submit(None)
                ).props("flat dense")

            with ui.card().props("bordered flat").classes("w-full"):
                with ui.list().props("dense separator").classes("w-full"):
                    info = {
                        _("Name"): row["name"],
                        _("Backend"): row["backend"],
                        _("Active"): row["active"],
                        _("Secret"): row["secrets"],
                        _("Last Tested"): row["tested"],
                        _("Test Result"): row["result"],
                        _("Test Message"): row["last_test_message"],
                    }
                    for key, value in info.items():
                        with ui.item():
                            with ui.row(wrap=False).classes("w-full items-center"):
                                ui.label(key).classes("font-bold w-2/7")
                                ui.label(value).classes("w-5/7 text-pretty break-words")

            public_config = row["public_config"] or {}
            if public_config:
                with ui.expansion(_("Public configuration"), icon="tune").classes(
                    "w-full"
                ):
                    with ui.list().props("dense separator").classes("w-full"):
                        for key, value in public_config.items():
                            with ui.item():
                                with ui.row(wrap=False).classes("w-full items-center"):
                                    ui.label(str(key)).classes("font-bold w-2/7")
                                    ui.label(str(value)).classes(
                                        "w-5/7 text-pretty break-words"
                                    )

            async def on_edit():
                profile_dialog.submit(None)
                await open_profile_editor(row)

            async def on_test():
                await test_profile(row)
                profile_dialog.submit(None)

            async def on_activate():
                await activate_profile(row)
                profile_dialog.submit(None)

            async def on_delete():
                await delete_profile(row)
                profile_dialog.submit(None)

            with ui.grid(columns=4).classes("w-full gap-2"):
                ui.button(_("Edit"), icon="edit", on_click=on_edit)
                ui.button(_("Test"), icon="fact_check", on_click=on_test)
                ui.button(
                    _("Activate"),
                    icon="published_with_changes",
                    on_click=on_activate,
                )
                ui.button(
                    _("Delete"),
                    icon="delete",
                    color=theme().negative,
                    on_click=on_delete,
                )

        await profile_dialog

    async def handle_row_click(e):
        _click_event_params, row, _click_index = e.args
        profile_table.selected = [row]
        await open_profile_dialog(row)

    async def handle_info_click(e):
        await open_profile_dialog(e.args)

    profile_table.on("row-click", handle_row_click)
    profile_table.on("info", handle_info_click)
    await refresh_profiles()


async def _render_user_section(user_manager):
    ui.label(_("User management")).classes("text-2xl font-bold")

    allow_registration = ui.switch(
        _("Allow registration"),
        value=await user_manager.is_registration_allowed(),
    )

    async def on_registration_change():
        await user_manager.set_registration_allowed(bool(allow_registration.value))
        notify.success(_("Registration setting saved."))

    allow_registration.on("update:model-value", on_registration_change)

    with ui.row().classes("w-full items-end gap-3"):
        user_query = (
            ui.input(_("Search users"))
            .props("dense clearable")
            .classes("flex-1 min-w-64")
        )
        include_deleted = ui.checkbox(_("Show deleted users"), value=False).classes(
            "pb-2"
        )
    total_label = ui.label().classes("text-sm text-gray-500 pb-2")
    page_state = {"offset": 0, "limit": 20, "total": 0}
    mode_state = {"batch": False}

    with ui.row().classes("w-full items-center gap-2") as normal_toolbar:
        ui.button(
            _("Create user"),
            icon="person_add",
            on_click=lambda: open_create_user_dialog(),
        )
        ui.button(_("Search"), icon="search", on_click=lambda: refresh_users(True))
        ui.button(_("Previous"), icon="chevron_left", on_click=lambda: previous_page())
        ui.button(_("Next"), icon="chevron_right", on_click=lambda: next_page())
        ui.button(
            _("Batch select"),
            icon="check_box",
            on_click=lambda: set_batch_mode(True),
        )

    with ui.row().classes("w-full items-center gap-2") as batch_toolbar:
        ui.button(
            _("Enable selected"),
            icon="check_circle",
            on_click=lambda: batch_set_active(True),
        )
        ui.button(
            _("Disable selected"),
            icon="block",
            on_click=lambda: batch_set_active(False),
        )
        ui.button(
            _("Revoke sessions"),
            icon="logout",
            on_click=lambda: batch_revoke_sessions(),
        )
        ui.button(
            _("Delete"),
            icon="delete",
            color=theme().negative,
            on_click=lambda: batch_soft_delete(),
        )
        ui.button(
            _("Done"),
            icon="check_box_outline_blank",
            on_click=lambda: set_batch_mode(False),
        )
    batch_toolbar.visible = False

    user_table = ui.table(
        columns=[
            {"name": "email", "label": _("Email"), "field": "email", "align": "left"},
            {"name": "active", "label": _("Active"), "field": "active"},
            {"name": "admin", "label": _("Admin"), "field": "admin"},
            {"name": "quota", "label": _("Quota"), "field": "quota"},
            {"name": "usage", "label": _("Used"), "field": "usage"},
            {"name": "deleted", "label": _("Deleted"), "field": "deleted"},
            {"name": "created_at", "label": _("Created At"), "field": "created_at"},
            {
                "name": "action",
                "label": _("Action"),
                "field": "action",
                "align": "center",
                "sortable": False,
                "style": "width: 0px",
            },
        ],
        rows=[],
        row_key="email",
        selection="single",
        pagination={"rowsPerPage": 20},
    ).classes("w-full")

    user_table.add_slot(
        "body-cell-action",
        f"""
        <q-td :props="props">
            <q-btn icon="info" @click.stop="$parent.$emit('info', props.row)" class="text-primary" flat dense>
                <q-tooltip>{_("Show user information")}</q-tooltip>
            </q-btn>
        </q-td>
    """,
    )

    async def refresh_users(reset_offset: bool = False):
        if reset_offset:
            page_state["offset"] = 0
        users, total = await user_manager.list_users(
            offset=page_state["offset"],
            limit=page_state["limit"],
            query=user_query.value or None,
            include_deleted=bool(include_deleted.value),
        )
        page_state["total"] = total
        rows = []
        for user in users:
            usage = 0 if user.deleted_at else await get_user_storage_usage(user.id)
            rows.append(_build_user_table_row(user, usage))
        user_table.rows = rows
        user_table.selected = []
        user_table.update()
        total_label.text = _("Users {start}-{end} of {total}").format(
            start=page_state["offset"] + 1 if total else 0,
            end=min(page_state["offset"] + page_state["limit"], total),
            total=total,
        )
        total_label.update()

    async def open_create_user_dialog():
        with ui.dialog() as create_dialog, ui.card().classes("w-full max-w-2xl"):
            ui.label(_("Create user")).classes("text-lg font-bold")
            with ui.grid(columns=2).classes("w-full gap-3"):
                create_email = ui.input(_("Email")).props("dense").classes("w-full")
                create_password = (
                    ui.input(_("Password"), password=True, password_toggle_button=True)
                    .props("dense")
                    .classes("w-full")
                )
                create_quota_gib = (
                    ui.number(_("Quota GiB"), value=10, min=0, format="%.0f")
                    .props("dense")
                    .classes("w-full")
                )
                with ui.row().classes("items-center gap-4"):
                    create_active = ui.checkbox(_("Active"), value=True)
                    create_admin = ui.checkbox(_("Admin"), value=False)
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button(_("Cancel"), on_click=lambda: create_dialog.submit(None))
                ui.button(
                    _("Create user"),
                    icon="person_add",
                    on_click=lambda: create_dialog.submit(
                        {
                            "email": create_email.value,
                            "password": create_password.value,
                            "quota_gib": create_quota_gib.value,
                            "active": create_active.value,
                            "admin": create_admin.value,
                        }
                    ),
                )

        values = await create_dialog
        if not values:
            return
        try:
            quota_bytes = int(float(values["quota_gib"] or 0) * 1024**3)
            await user_manager.create_user(
                email=values["email"],
                password=values["password"],
                is_superuser=bool(values["admin"]),
                is_active=bool(values["active"]),
                quota_bytes=quota_bytes,
            )
        except Exception as exc:
            notify.error(str(exc))
            return
        notify.success(_("User created successfully."))
        await refresh_users(reset_offset=True)

    async def show_password_dialog(email: str, password: str):
        with ui.dialog() as password_dialog, ui.card().classes("w-full max-w-md"):
            ui.label(_("New password")).classes("text-lg font-bold")
            ui.label(email).classes("text-sm text-gray-500")
            ui.input(value=password).props("readonly").classes("w-full")
            ui.button(_("Close"), on_click=lambda: password_dialog.submit(None))
        await password_dialog

    async def open_user_dialog(row: dict):
        with ui.dialog() as user_dialog, ui.card().classes("w-full max-w-2xl"):
            with ui.row().classes("w-full justify-between items-center"):
                ui.label(_("User information")).classes("text-lg font-bold")
                ui.button(
                    icon="close", on_click=lambda: user_dialog.submit(None)
                ).props("flat dense")

            with ui.card().props("bordered flat").classes("w-full"):
                with ui.list().props("dense separator").classes("w-full"):
                    info = {
                        _("Email"): row["email"],
                        _("Active"): row["active"],
                        _("Admin"): row["admin"],
                        _("Quota"): row["quota"],
                        _("Used"): row["usage"],
                        _("Created At"): row["created_at"],
                        _("Deleted"): row["deleted"],
                    }
                    for key, value in info.items():
                        with ui.item():
                            with ui.row(wrap=False).classes("w-full items-center"):
                                ui.label(key).classes("font-bold w-2/7")
                                ui.label(value).classes("w-5/7 text-pretty break-words")

            async def toggle_active():
                try:
                    await user_manager.set_active(
                        email=row["email"],
                        is_active=not row["is_active"],
                    )
                except Exception as exc:
                    notify.error(str(exc))
                    return
                notify.success(_("User status updated."))
                user_dialog.submit(None)
                await refresh_users()

            async def toggle_admin():
                try:
                    await user_manager.set_superuser(
                        email=row["email"],
                        is_superuser=not row["is_superuser"],
                    )
                except Exception as exc:
                    notify.error(str(exc))
                    return
                notify.success(_("User role updated."))
                user_dialog.submit(None)
                await refresh_users()

            async def reset_random_password():
                confirm = await ConfirmDialog(
                    _("Reset password"),
                    _("Generate a new random password for {email}?").format(
                        email=row["email"]
                    ),
                    warning=True,
                ).open()
                if not confirm:
                    return
                try:
                    new_password = await user_manager.admin_reset_password(
                        email=row["email"]
                    )
                except Exception as exc:
                    notify.error(str(exc))
                    return
                await show_password_dialog(row["email"], new_password)

            async def set_quota():
                with ui.dialog() as quota_dialog, ui.card().classes("w-full max-w-md"):
                    ui.label(_("Set quota")).classes("text-lg font-bold")
                    ui.label(row["email"]).classes("text-sm text-gray-500")
                    quota_gib = (
                        ui.number(
                            _("Quota GiB"),
                            value=round((row["quota_bytes"] or 0) / 1024**3),
                            min=0,
                            format="%.0f",
                        )
                        .props("dense")
                        .classes("w-full")
                    )
                    with ui.row().classes("w-full justify-end gap-2"):
                        ui.button(
                            _("Cancel"), on_click=lambda: quota_dialog.submit(None)
                        )
                        ui.button(
                            _("Save"),
                            icon="save",
                            on_click=lambda: quota_dialog.submit(quota_gib.value),
                        )
                value = await quota_dialog
                if value is None:
                    return
                try:
                    quota_bytes = int(float(value or 0) * 1024**3)
                    await user_manager.set_quota(
                        email=row["email"], quota_bytes=quota_bytes
                    )
                except Exception as exc:
                    notify.error(str(exc))
                    return
                notify.success(_("Quota updated."))
                user_dialog.submit(None)
                await refresh_users()

            async def revoke_sessions():
                try:
                    await user_manager.revoke_sessions(email=row["email"])
                except Exception as exc:
                    notify.error(str(exc))
                    return
                notify.success(_("User sessions revoked."))
                user_dialog.submit(None)
                await refresh_users()

            async def soft_delete_user():
                confirm = await ConfirmDialog(
                    _("Delete user"),
                    _("Soft delete {email}? Files are preserved.").format(
                        email=row["email"]
                    ),
                    warning=True,
                ).open()
                if not confirm:
                    return
                try:
                    await user_manager.soft_delete_user(email=row["email"])
                except Exception as exc:
                    notify.error(str(exc))
                    return
                notify.success(_("User deleted."))
                user_dialog.submit(None)
                await refresh_users()

            if not row["is_deleted"]:
                with ui.grid(columns=3).classes("w-full gap-2"):
                    ui.button(
                        _("Enable/Disable"),
                        icon="block",
                        on_click=toggle_active,
                    )
                    ui.button(
                        _("Toggle admin"),
                        icon="admin_panel_settings",
                        on_click=toggle_admin,
                    )
                    ui.button(
                        _("Reset password"),
                        icon="password",
                        on_click=reset_random_password,
                    )
                    ui.button(_("Set quota"), icon="data_usage", on_click=set_quota)
                    ui.button(
                        _("Revoke sessions"),
                        icon="logout",
                        on_click=revoke_sessions,
                    )
                    ui.button(
                        _("Delete"),
                        icon="delete",
                        color=theme().negative,
                        on_click=soft_delete_user,
                    )

        await user_dialog

    async def handle_row_click(e):
        if mode_state["batch"]:
            return
        _click_event_params, row, _click_index = e.args
        user_table.selected = [row]
        await open_user_dialog(row)

    async def handle_info_click(e):
        await open_user_dialog(e.args)

    async def previous_page():
        page_state["offset"] = max(0, page_state["offset"] - page_state["limit"])
        await refresh_users()

    async def next_page():
        if page_state["offset"] + page_state["limit"] < page_state["total"]:
            page_state["offset"] += page_state["limit"]
        await refresh_users()

    async def batch_set_active(is_active: bool):
        rows = _modifiable_user_rows(user_table.selected)
        if not rows:
            notify.warning(_("Please select at least one active user."))
            return
        confirm = await ConfirmDialog(
            _("Update user status"),
            [
                _("Update {count} selected users?").format(count=len(rows)),
                *[row["email"] for row in rows],
            ],
            warning=True,
        ).open()
        if not confirm:
            return
        success = 0
        for row in rows:
            try:
                await user_manager.set_active(email=row["email"], is_active=is_active)
            except Exception as exc:
                notify.error(str(exc))
            else:
                success += 1
        notify.success(_("Updated {count} users.").format(count=success))
        await refresh_users()

    async def batch_revoke_sessions():
        rows = _modifiable_user_rows(user_table.selected)
        if not rows:
            notify.warning(_("Please select at least one active user."))
            return
        confirm = await ConfirmDialog(
            _("Revoke sessions"),
            [
                _("Revoke sessions for {count} selected users?").format(
                    count=len(rows)
                ),
                *[row["email"] for row in rows],
            ],
            warning=True,
        ).open()
        if not confirm:
            return
        success = 0
        for row in rows:
            try:
                await user_manager.revoke_sessions(email=row["email"])
            except Exception as exc:
                notify.error(str(exc))
            else:
                success += 1
        notify.success(_("Revoked sessions for {count} users.").format(count=success))
        await refresh_users()

    async def batch_soft_delete():
        rows = _modifiable_user_rows(user_table.selected)
        if not rows:
            notify.warning(_("Please select at least one active user."))
            return
        confirm = await ConfirmDialog(
            _("Delete users"),
            [
                _("Soft delete {count} selected users? Files are preserved.").format(
                    count=len(rows)
                ),
                *[row["email"] for row in rows],
            ],
            warning=True,
        ).open()
        if not confirm:
            return
        success = 0
        for row in rows:
            try:
                await user_manager.soft_delete_user(email=row["email"])
            except Exception as exc:
                notify.error(str(exc))
            else:
                success += 1
        notify.success(_("Deleted {count} users.").format(count=success))
        await refresh_users()

    def set_batch_mode(enabled: bool):
        mode_state["batch"] = enabled
        user_table.set_selection("multiple" if enabled else "single")
        user_table.selected = []
        normal_toolbar.visible = not enabled
        batch_toolbar.visible = enabled
        normal_toolbar.update()
        batch_toolbar.update()
        user_table.update()
        if enabled:
            notify.info(_("Multiple selection enabled"))

    user_query.on("keydown.enter", lambda _e: refresh_users(True))
    include_deleted.on("update:model-value", lambda _e: refresh_users(True))
    user_table.on("row-click", handle_row_click)
    user_table.on("info", handle_info_click)
    await refresh_users()


def _render_system_section():
    ui.label(_("System status")).classes("text-2xl font-bold")
    with ui.grid(columns=3).classes("w-full gap-3"):
        cpu_card = _stat_card(_("CPU usage"), "-")
        memory_card = _stat_card(_("Memory usage"), "-")
        disk_card = _stat_card(_("Disk usage"), "-")
        app_memory_card = _stat_card(_("Application memory"), "-")
        load_card = _stat_card(_("Load average"), "-")

    def update_metrics():
        metrics = get_system_metrics()
        cpu_card.text = f"{metrics['cpu']:.0f}%"
        memory_card.text = (
            f"{metrics['memory_percent']:.0f}% "
            f"({metrics['memory_used']:.1f}/{metrics['memory_total']:.1f} GiB)"
        )
        disk_card.text = f"{metrics['disk_percent']:.0f}%"
        app_memory_card.text = f"{metrics['process_memory']:.1f} MB"
        load_card.text = "{a:.2f} {b:.2f} {c:.2f}".format(
            a=metrics["system_load"][0],
            b=metrics["system_load"][1],
            c=metrics["system_load"][2],
        )
        for label in [cpu_card, memory_card, disk_card, app_memory_card, load_card]:
            label.update()

    update_metrics()
    return ui.timer(2.0, update_metrics)


def _render_developer_section():
    ui.label(_("Developer tools")).classes("text-2xl font-bold")
    ui.label(_("These tools are intended for maintenance and debugging.")).classes(
        "text-sm text-gray-500"
    )

    with ui.row().classes("w-full gap-2"):
        ui.button(_("Run garbage collection"), on_click=gc.collect)
        ui.button(
            _("Show object count"),
            on_click=lambda: notify.info(
                _("Object count: {count}").format(count=len(gc.get_objects()))
            ),
        )
        app_reload_button = ui.button(_("Reload app"), color=theme().negative)

    @require_user(superuser=True)
    async def on_app_reload_click():
        confirm = await ConfirmDialog(
            title=_("Reload app"),
            message=_("This will restart the application. Continue?"),
            warning=True,
        ).open()
        if confirm:
            notify.warning(
                _("Restarting {app_name}…").format(app_name=settings.APP_NAME)
            )
            app.shutdown()

    app_reload_button.on("click", on_app_reload_click)

    @require_user(superuser=True)
    def on_app_storage_general_change(e):
        data = e.content["json"]
        app.storage.general.clear()
        app.storage.general.update(data)

    @require_user(superuser=True)
    def on_app_storage_user_change(e):
        data = e.content["json"]
        app.storage.user.clear()
        app.storage.user.update(data)

    @require_user(superuser=True)
    def on_app_storage_client_change(e):
        data = e.content["json"]
        app.storage.client.clear()
        app.storage.client.update(data)

    @require_user(superuser=True)
    def on_app_storage_browser_change(e):
        data = e.content["json"]
        app.storage.browser.clear()
        app.storage.browser.update(data)

    with ui.expansion(_("NiceGUI storage editors"), icon="data_object").classes(
        "w-full"
    ):
        ui.label(_("Global storage")).classes("font-bold")
        ui.json_editor(
            {"content": {"json": app.storage.general}},
            on_change=on_app_storage_general_change,
        ).classes("w-full").style(style)

        ui.label(_("User storage")).classes("font-bold")
        ui.json_editor(
            {"content": {"json": app.storage.user}},
            on_change=on_app_storage_user_change,
        ).classes("w-full").style(style)

        ui.label(_("Client storage")).classes("font-bold")
        ui.json_editor(
            {"content": {"json": app.storage.client}},
            on_change=on_app_storage_client_change,
        ).classes("w-full").style(style)

        ui.label(_("Browser storage")).classes("font-bold")
        ui.json_editor(
            {"content": {"json": app.storage.browser}},
            on_change=on_app_storage_browser_change,
        ).classes("w-full").style(style)


def _stat_card(title: str, value: str):
    with ui.column().classes("border rounded p-3 min-h-24 gap-1"):
        ui.label(title).classes("text-sm text-gray-500")
        value_label = ui.label(value).classes("text-lg font-bold break-all")
    return value_label
