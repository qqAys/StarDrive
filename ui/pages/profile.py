from fastapi.responses import RedirectResponse
from nicegui import ui, APIRouter, app

from config import settings
from ui.components.base import base_layout
from ui.components.notify import notify
from utils import _, SUPPORTED_LANGUAGES

this_page_routes = "/profile"


@app.get("/")
def index():
    return RedirectResponse(this_page_routes + "/")


@app.get(this_page_routes)
def browser_index():
    return RedirectResponse(this_page_routes + "/")


router = APIRouter(prefix=this_page_routes)


@router.page("/")
@base_layout(header=True, footer=True, args={"title": _("Profile")})
async def index():

    def change_language(lang_code):
        current_lang_code = app.storage.user.get("default_lang", "en_US")
        if current_lang_code != lang_code:
            app.storage.user["default_lang"] = lang_code
            notify.success(_("Language changed to {}").format(lang_code))
            ui.timer(
                settings.NICEGUI_TIMER_INTERVAL,
                lambda: ui.navigate.to(this_page_routes),
            )

    with ui.dropdown_button(icon="translate", auto_close=True):
        for lang in SUPPORTED_LANGUAGES:
            ui.item(lang, on_click=lambda lang_code=lang: change_language(lang_code))
