import gc
import os

import psutil
from fastapi.requests import Request
from nicegui import Client, ui, app, APIRouter
from starlette.responses import RedirectResponse

from app.config import settings
from app.core.i18n import _
from app.security.guards import require_user
from app import globals
from app.services.file_service import get_user_storage_usage
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
    """
    Collect key system and application performance metrics.

    Returns:
        dict: A dictionary containing CPU, memory, disk, and load average statistics.
    """
    cpu_percent = psutil.cpu_percent(interval=None)
    memory_info = psutil.virtual_memory()
    process_memory = get_process_memory()
    disk_usage = psutil.disk_usage("/")
    system_load = psutil.getloadavg()

    return {
        "cpu": cpu_percent,
        "memory_percent": memory_info.percent,
        "memory_total": round(memory_info.total / (1024**3), 2),
        "memory_used": round(memory_info.used / (1024**3), 2),
        "process_memory": round(process_memory / (1024**2), 2),
        "disk_percent": disk_usage.percent,
        "system_load": system_load,
    }


@router.page("/")
@require_user(superuser=True)
async def console_page(request: Request, client: Client):
    """
    Render the admin console page for superusers.

    This page provides:
    - System resource monitoring (CPU, memory, disk, load)
    - Application memory inspection and garbage collection
    - App restart functionality
    - Real-time editing of global, user, client, and browser storage
    """
    async with BaseLayout().render(
        header=True,
        footer=True,
        args={"title": _("Console")},
    ):
        user_manager = globals.get_user_manager()

        with ui.column().classes("w-full"):
            ui.label(_("User management")).classes("text-lg font-bold")

            allow_registration = ui.switch(
                _("Allow registration"),
                value=await user_manager.is_registration_allowed(),
            )

            async def on_registration_change():
                await user_manager.set_registration_allowed(
                    bool(allow_registration.value)
                )
                notify.success(_("Registration setting saved."))

            allow_registration.on("update:model-value", on_registration_change)

            with ui.card().props("flat bordered").classes("w-full"):
                ui.label(_("Create user")).classes("font-bold")
                with ui.grid(columns=5).classes("w-full gap-2 items-end"):
                    create_email = ui.input(_("Email")).props("dense")
                    create_password = ui.input(
                        _("Password"), password=True, password_toggle_button=True
                    ).props("dense")
                    create_quota_gib = ui.number(
                        _("Quota GiB"), value=10, min=0, format="%.0f"
                    ).props("dense")
                    create_active = ui.checkbox(_("Active"), value=True)
                    create_admin = ui.checkbox(_("Admin"), value=False)

                async def create_user():
                    try:
                        quota_bytes = int(float(create_quota_gib.value or 0) * 1024**3)
                        await user_manager.create_user(
                            email=create_email.value,
                            password=create_password.value,
                            is_superuser=bool(create_admin.value),
                            is_active=bool(create_active.value),
                            quota_bytes=quota_bytes,
                        )
                    except Exception as exc:
                        notify.error(str(exc))
                        return
                    create_password.value = ""
                    notify.success(_("User created successfully."))
                    await refresh_users()

                ui.button(_("Create user"), icon="person_add", on_click=create_user)

            user_query = (
                ui.input(_("Search users")).props("dense clearable").classes("w-full")
            )
            user_table = ui.table(
                columns=[
                    {
                        "name": "email",
                        "label": _("Email"),
                        "field": "email",
                        "align": "left",
                    },
                    {"name": "active", "label": _("Active"), "field": "active"},
                    {"name": "admin", "label": _("Admin"), "field": "admin"},
                    {"name": "quota", "label": _("Quota"), "field": "quota"},
                    {"name": "usage", "label": _("Used"), "field": "usage"},
                    {
                        "name": "created_at",
                        "label": _("Created At"),
                        "field": "created_at",
                    },
                ],
                rows=[],
                row_key="email",
                selection="single",
                pagination={"rowsPerPage": 10},
            ).classes("w-full")

            def selected_user():
                if not user_table.selected:
                    notify.warning(_("Please select a user."))
                    return None
                return user_table.selected[0]

            async def refresh_users():
                users, _total = await user_manager.list_users(
                    offset=0,
                    limit=200,
                    query=user_query.value or None,
                )
                rows = []
                for user in users:
                    usage = await get_user_storage_usage(user.id)
                    rows.append(
                        {
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
                            "created_at": user.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                        }
                    )
                user_table.rows = rows
                user_table.selected = []
                user_table.update()

            async def toggle_active():
                row = selected_user()
                if not row:
                    return
                await user_manager.set_active(
                    email=row["email"],
                    is_active=not row["is_active"],
                )
                notify.success(_("User status updated."))
                await refresh_users()

            async def toggle_admin():
                row = selected_user()
                if not row:
                    return
                await user_manager.set_superuser(
                    email=row["email"],
                    is_superuser=not row["is_superuser"],
                )
                notify.success(_("User role updated."))
                await refresh_users()

            async def reset_random_password():
                row = selected_user()
                if not row:
                    return
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
                with (
                    ui.dialog() as password_dialog,
                    ui.card().classes("w-full max-w-md"),
                ):
                    ui.label(_("New password")).classes("text-lg font-bold")
                    ui.label(row["email"]).classes("text-sm text-gray-500")
                    ui.input(value=new_password).props("readonly").classes("w-full")
                    ui.button(_("Close"), on_click=password_dialog.close)
                password_dialog.open()

            async def set_selected_quota():
                row = selected_user()
                if not row:
                    return
                try:
                    quota_bytes = int(float(quota_gib.value or 0) * 1024**3)
                    await user_manager.set_quota(
                        email=row["email"],
                        quota_bytes=quota_bytes,
                    )
                except Exception as exc:
                    notify.error(str(exc))
                    return
                notify.success(_("Quota updated."))
                await refresh_users()

            with ui.row().classes("w-full items-end gap-2"):
                ui.button(_("Refresh"), icon="refresh", on_click=refresh_users)
                ui.button(_("Enable/Disable"), icon="block", on_click=toggle_active)
                ui.button(
                    _("Toggle admin"),
                    icon="admin_panel_settings",
                    on_click=toggle_admin,
                )
                ui.button(
                    _("Reset password"), icon="password", on_click=reset_random_password
                )
                quota_gib = ui.number(
                    _("Quota GiB"), value=10, min=0, format="%.0f"
                ).props("dense")
                ui.button(
                    _("Set quota"), icon="data_usage", on_click=set_selected_quota
                )

            user_query.on("keydown.enter", refresh_users)
            await refresh_users()

            ui.separator()

            # Service URL input
            ui.input(_("Service URL")).bind_value(
                app.storage.general,
                "service_url",
            )

            ui.separator()

            # Dynamic metric labels
            system_load_label = ui.label().classes("font-bold")
            process_memory_label = ui.label().classes("font-bold")

            ui.separator()

            # Resource usage progress bars
            ui.label(_("CPU usage")).classes("font-bold")
            cpu_progress = ui.linear_progress(value=0, color="teal").props("stripe")

            ui.label(_("Memory usage")).classes("font-bold")
            memory_progress = ui.linear_progress(value=0, color="blue").props("stripe")

            ui.label(_("Disk usage (root)")).classes("font-bold")
            disk_progress = ui.linear_progress(value=0, color="orange").props("stripe")

            ui.separator()

            # Utility buttons
            with ui.row().classes("w-full"):
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
                """Prompt confirmation before restarting the application."""
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

            ui.separator()

            # Storage editors with change handlers
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

            with ui.column().classes("w-full"):
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

        # Periodic metrics updater
        def update_metrics():
            metrics = get_system_metrics()

            cpu_progress.value = round(metrics["cpu"] / 100, 2)
            memory_progress.value = round(metrics["memory_percent"] / 100, 2)
            disk_progress.value = round(metrics["disk_percent"] / 100, 2)

            process_memory_label.text = _("{app_name} memory usage: {value} MB").format(
                app_name=settings.APP_NAME,
                value=metrics["process_memory"],
            )

            system_load_label.text = _("Host load average: {a} {b} {c}").format(
                a=f"{metrics['system_load'][0]:.2f}",
                b=f"{metrics['system_load'][1]:.2f}",
                c=f"{metrics['system_load'][2]:.2f}",
            )

            cpu_progress.update()
            memory_progress.update()
            disk_progress.update()
            system_load_label.update()

        update_metrics_timer = ui.timer(2.0, update_metrics)

        @ui.context.client.on_delete
        def disconnect():
            """Clean up the periodic timer when the client disconnects."""
            update_metrics_timer.deactivate()
            update_metrics_timer.cancel()
            update_metrics_timer.delete()
