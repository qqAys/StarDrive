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

this_page_routes = "/console"


@app.get(this_page_routes)
def browser_index():
    return RedirectResponse(this_page_routes + "/")


router = APIRouter(prefix=this_page_routes)


def get_process_memory() -> int:
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    return mem_info.rss


def get_system_metrics():
    """Get CPU, memory and disk usage"""
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
    async with BaseLayout().render(
        header=True, footer=True, args={"title": _("Console")}
    ):
        with ui.column().classes("w-full"):
            ui.input(_("Service URL")).bind_value(app.storage.general, "service_url")

            ui.separator()

            system_load_label = ui.label().classes("font-bold")
            process_memory_label = ui.label().classes("font-bold")

            ui.separator()

            ui.label(_("CPU Usage")).classes("font-bold")
            cpu_progress = ui.linear_progress(value=0, color="teal").props("stripe")

            ui.label(_("Memory Usage")).classes("font-bold")
            memory_progress = ui.linear_progress(value=0, color="blue").props("stripe")

            ui.label(_("Disk Usage (Root Filesystem)")).classes("font-bold")
            disk_progress = ui.linear_progress(value=0, color="orange").props("stripe")

            ui.separator()

            with ui.row().classes("w-full"):
                ui.button(_("Run Full GC"), on_click=gc.collect)
                ui.button(
                    _("Show Object Reference Count"),
                    on_click=lambda: notify.info(
                        _("Object reference count: {count}").format(
                            count=len(gc.get_objects())
                        )
                    ),
                )

                app_reload_button = ui.button(_("APP RELOAD"), color="red")

            async def on_app_reload_click():
                confirm = await ConfirmDialog(
                    title=_("APP RELOAD"),
                    message=_("Are you sure you want to reload the application?"),
                ).open()

                if confirm:
                    notify.warning(_("Reloading {}...").format(settings.APP_NAME))
                    app.shutdown()

            app_reload_button.on("click", on_app_reload_click)

            ui.separator()

            def on_app_storage_general_change(e):
                new_data = e.content["json"]
                app.storage.general.clear()
                app.storage.general.update(new_data)

            def on_app_storage_user_change(e):
                new_data = e.content["json"]
                app.storage.user.clear()
                app.storage.user.update(new_data)

            def on_app_storage_client_change(e):
                new_data = e.content["json"]
                app.storage.client.clear()
                app.storage.client.update(new_data)

            def on_app_storage_browser_change(e):
                new_data = e.content["json"]
                app.storage.browser.clear()
                app.storage.browser.update(new_data)

            with ui.column().classes("w-full"):
                ui.label(_("app.storage.general")).classes("font-bold")
                ui.json_editor(
                    {"content": {"json": app.storage.general}},
                    on_change=on_app_storage_general_change,
                ).classes("w-full").style(style)

                ui.label(_("app.storage.user")).classes("font-bold")
                ui.json_editor(
                    {"content": {"json": app.storage.user}},
                    on_change=on_app_storage_user_change,
                ).classes("w-full").style(style)

                ui.label(_("app.storage.client")).classes("font-bold")
                ui.json_editor(
                    {"content": {"json": app.storage.client}},
                    on_change=on_app_storage_client_change,
                ).classes("w-full").style(style)

                ui.label(_("app.storage.browser")).classes("font-bold")
                ui.json_editor(
                    {"content": {"json": app.storage.browser}},
                    on_change=on_app_storage_browser_change,
                ).classes("w-full").style(style)

        def update_metrics():
            metrics = get_system_metrics()

            cpu_progress.value = round(metrics["cpu"] / 100, 1)
            memory_progress.value = round(metrics["memory_percent"] / 100, 1)
            disk_progress.value = round(metrics["disk_percent"] / 100, 1)

            process_memory_label.text = _("{} Memory Usage: {} MB").format(settings.APP_NAME, metrics["process_memory"],)

            system_load_label.text = _(
                "Host Load Average: {} {} {}"
            ).format(
                f"{metrics['system_load'][0]:.2f}",
                f"{metrics['system_load'][1]:.2f}",
                f"{metrics['system_load'][2]:.2f}",
            )

            cpu_progress.update()
            memory_progress.update()
            disk_progress.update()
            system_load_label.update()

        update_metrics_timer = ui.timer(2.0, update_metrics)

        @ui.context.client.on_delete
        def disconnect():
            update_metrics_timer.deactivate()
            update_metrics_timer.cancel()
            update_metrics_timer.delete()
