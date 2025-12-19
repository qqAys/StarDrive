import traceback

from nicegui import ui

from app.config import settings
from app.core.i18n import _


def render_404(
    request_uuid: str,
    exception: str = _("Page not found"),
    custom_note: str = None,
    back_button: bool = True,
):
    ui.colors(primary=settings.APP_PRIMARY_COLOR)
    ui.add_head_html(
        """
    <style>
    html, body {
        height: 100%;
        margin: 0;
        overflow: hidden;
    }
    </style>
    """
    )

    ui.page_title(f"404 | {settings.APP_NAME}")

    with ui.column().classes(
        "flex justify-center items-center h-screen w-full text-center flex-nowrap"
    ):
        ui.markdown(f"# 404 - {exception}").classes("text-base")
        if custom_note:
            ui.markdown(custom_note).classes("text-base")
        else:
            ui.markdown(
                _(
                    "You have reached a place where there is no one, but you are still in {}. 🧐"
                ).format(settings.APP_NAME)
            ).classes("text-base")
        ui.markdown(_("request_uuid = `{}`").format(request_uuid)).classes("text-xs")
        with ui.row().classes("mt-4 gap-4"):
            if back_button:
                ui.button(_("Back"), icon="arrow_back", on_click=ui.navigate.back)
            ui.button(_("Home"), icon="home", on_click=lambda: ui.navigate.to("/home/"))


def render_50x(request_uuid: str, exception: str = ""):
    ui.colors(primary=settings.APP_PRIMARY_COLOR)
    ui.add_head_html(
        """
    <style>
    html, body {
        height: 100%;
        margin: 0;
        overflow: hidden;
    }
    </style>
    """
    )

    ui.page_title(f"500 | {settings.APP_NAME}")

    error_traceback = traceback.format_exc(chain=False)

    with ui.column().classes(
        "flex justify-center items-center h-screen w-full text-center flex-nowrap"
    ):
        ui.markdown(_("# 500 - Server internal error")).classes("text-base")
        ui.markdown(
            _("A problem {} couldn't handle occurred, great job. 😅").format(
                settings.APP_NAME
            )
        ).classes("text-base")
        if settings.DEBUG:
            ui.markdown(f"### `{exception}`")
            ui.code(error_traceback).classes(
                "w-full overflow-auto text-sm text-left md:w-1/2"
            )
        ui.markdown(_("request_uuid = `{}`").format(request_uuid)).classes("text-xs")

        ui.markdown(
            _(
                "Please report this issue by opening a new issue on our GitHub repository. ⬇️"
            )
        ).classes("text-sm")

        BUG_REPORT_URL = f"{settings.APP_GITHUB_URL}/issues/new?template=bug_report.md&title=[BUG]{exception}"

        with ui.row().classes("mt-4 gap-4"):
            ui.button(_("Back"), icon="arrow_back", on_click=ui.navigate.back)
            ui.button(
                _("Report"),
                icon="bug_report",
                on_click=lambda: ui.navigate.to(BUG_REPORT_URL, new_tab=True),
            )
