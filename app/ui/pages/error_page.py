import traceback

from nicegui import ui

from app.config import settings
from app.core.i18n import _
from app.ui.theme import theme, set_theme, DefaultTheme


@ui.page("/404")
def not_found_page():
    """Render the standard 404 Not Found error page."""
    render_404()


def render_404(
    request_uuid: str | None = None,
    exception: str = _("Page not found"),
    custom_note: str | None = None,
    back_button: bool = True,
):
    """
    Render a user-friendly 404 error page.

    Args:
        request_uuid: Optional unique ID for the request (useful for support/debugging).
        exception: The main error message to display.
        custom_note: An optional additional note to show below the main message.
        back_button: Whether to show a "Back" navigation button.
    """
    set_theme(DefaultTheme)
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
        ui.markdown(f"# 404 · {exception}").classes("text-base")

        if custom_note:
            ui.markdown(custom_note).classes("text-base")
        else:
            ui.markdown(
                _("Nothing to see here, but you are still in {app_name}.").format(
                    app_name=settings.APP_NAME
                )
            ).classes("text-base")

        if request_uuid:
            ui.markdown(
                _("Request ID: `{request_id}`").format(request_id=request_uuid)
            ).classes("text-xs")

        with ui.row().classes("mt-4 gap-4"):
            if back_button:
                ui.button(_("Back"), icon="arrow_back", on_click=ui.navigate.back)
            ui.button(
                _("Home"),
                icon="home",
                on_click=lambda: ui.navigate.to("/home/"),
            )


def render_50x(request_uuid: str, exception: str = ""):
    """
    Render a 500-series internal server error page.

    In development mode (DEBUG=True), the full traceback is shown for debugging.
    In production, only a generic message and request ID are displayed.

    Args:
        request_uuid: Unique ID of the failed request (for support tracking).
        exception: Brief description of the error (used in bug report title).
    """
    set_theme(DefaultTheme)
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
        ui.markdown(_("# 500 · Internal server error")).classes("text-base")

        ui.markdown(
            _(
                "Something went wrong while {app_name} was processing your request."
            ).format(app_name=settings.APP_NAME)
        ).classes("text-base")

        if settings.DEBUG:
            ui.markdown(f"### `{exception}`")
            ui.code(error_traceback).classes(
                "w-full overflow-auto text-sm text-left md:w-1/2"
            )

        ui.markdown(
            _("Request ID: `{request_id}`").format(request_id=request_uuid)
        ).classes("text-xs")

        ui.markdown(
            _("Please help us improve by reporting this issue on GitHub.")
        ).classes("text-sm")

        bug_report_url = (
            f"{settings.APP_GITHUB_URL}/issues/new"
            f"?template=bug_report.md&title=[BUG]{exception}"
        )

        with ui.row().classes("mt-4 gap-4"):
            ui.button(_("Back"), icon="arrow_back", on_click=ui.navigate.back)
            ui.button(
                _("Report issue"),
                icon="bug_report",
                on_click=lambda: ui.navigate.to(bug_report_url, new_tab=True),
            )
