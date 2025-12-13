import gc
import os

import psutil
from fastapi.requests import Request
from nicegui import Client, ui, app, APIRouter
from starlette.responses import RedirectResponse

from config import settings
from services.file_service import clear_expired_download_links
from ui.components.base import base_layout
from ui.components.dialog import ConfirmDialog
from ui.components.json_edit import style
from ui.components.notify import notify
from utils import _

this_page_routes = "/console"


@app.get("/")
def index():
    return RedirectResponse(this_page_routes + "/")


@app.get(this_page_routes)
def browser_index():
    return RedirectResponse(this_page_routes + "/")


router = APIRouter(prefix=this_page_routes)


def get_process_memory() -> int:
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    return mem_info.rss


def get_system_metrics():
    """获取 CPU、内存和磁盘使用率"""
    cpu_percent = psutil.cpu_percent(interval=None)
    memory_info = psutil.virtual_memory()
    process_memory = get_process_memory()
    disk_usage = psutil.disk_usage("/")
    system_load = psutil.getloadavg()

    return {
        "cpu": cpu_percent,
        "memory_percent": memory_info.percent,
        "memory_total": round(memory_info.total / (1024**3), 2),  # 转换为 GB
        "memory_used": round(memory_info.used / (1024**3), 2),  # 转换为 GB
        "process_memory": round(process_memory / (1024**2), 2),  # 转换为 MB
        "disk_percent": disk_usage.percent,
        "system_load": system_load,
    }


@router.page("/")
@base_layout(header=True, footer=True, args={"title": _("Console")})
async def console_page(request: Request, client: Client):
    with ui.column().classes("w-full"):
        system_load_label = ui.label().classes("font-bold")
        process_memory_label = ui.label().classes("font-bold")

        ui.separator()

        # 标签和进度条用于 CPU
        ui.label("CPU 使用率").classes("font-bold")
        cpu_progress = ui.linear_progress(value=0, color="teal").props("stripe")

        # 标签和进度条用于内存
        ui.label("内存使用率").classes("font-bold")
        memory_progress = ui.linear_progress(value=0, color="blue").props("stripe")

        # 标签和进度条用于磁盘
        ui.label("磁盘使用率 (根目录)").classes("font-bold")
        disk_progress = ui.linear_progress(value=0, color="orange").props("stripe")

        ui.separator()

        with ui.row().classes("w-full"):
            ui.button("清除过期分享链接", on_click=clear_expired_download_links)
            ui.button("主动执行FULL GC", on_click=gc.collect)
            ui.button(
                "查看引用计数统计",
                on_click=lambda: notify.info(f"对象引用计数: {len(gc.get_objects())}"),
            )

            app_reload_button = ui.button("APP RELOAD", color="red")

        async def on_app_reload_click():
            confirm = await ConfirmDialog(
                title="APP RELOAD",
                message="是否确定要重新加载APP?",
            ).open()

            if confirm:
                notify.warning(f"{settings.APP_NAME} 正在重新加载...")
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
            ui.label("app.storage.general").classes("font-bold")
            ui.json_editor(
                {"content": {"json": app.storage.general}},
                on_change=on_app_storage_general_change,
            ).classes("w-full").style(style)

            ui.label("app.storage.user").classes("font-bold")
            ui.json_editor(
                {"content": {"json": app.storage.user}},
                on_change=on_app_storage_user_change,
            ).classes("w-full").style(style)

            ui.label("app.storage.client").classes("font-bold")
            ui.json_editor(
                {"content": {"json": app.storage.client}},
                on_change=on_app_storage_client_change,
            ).classes("w-full").style(style)

            ui.label("app.storage.browser").classes("font-bold")
            ui.json_editor(
                {"content": {"json": app.storage.browser}},
                on_change=on_app_storage_browser_change,
            ).classes("w-full").style(style)

    def update_metrics():
        metrics = get_system_metrics()

        cpu_progress.value = round(metrics["cpu"] / 100, 1)
        memory_progress.value = round(metrics["memory_percent"] / 100, 1)
        disk_progress.value = round(metrics["disk_percent"] / 100, 1)
        process_memory_label.text = (
            f"{settings.APP_NAME} 内存使用: {metrics["process_memory"]} MB"
        )
        system_load_label.text = f"宿主机负载: {metrics["system_load"][0]:.2f} {metrics["system_load"][1]:.2f} {metrics["system_load"][2]:.2f}"

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
