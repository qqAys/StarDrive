import gc
import os

import psutil
from fastapi.requests import Request
from nicegui import Client, ui, app, APIRouter
from starlette.responses import RedirectResponse

from app.config import settings
from app.core.i18n import _
from app.security.guards import require_user
from app.ui.components.base import BaseLayout
from app.ui.components.dialog import ConfirmDialog
from app.ui.components.json_edit import style
from app.ui.components.notify import notify
from app.ui.theme import theme

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
        with ui.column().classes("w-full"):
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
