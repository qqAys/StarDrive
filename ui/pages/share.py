from nicegui import ui, app, APIRouter
from starlette.responses import RedirectResponse

import globals
from ui.components.base import BaseLayout
from utils import _

this_page_routes = "/share"


@app.get("/")
def index():
    return RedirectResponse(this_page_routes + "/")


@app.get(this_page_routes)
def browser_index():
    return RedirectResponse(this_page_routes + "/")


router = APIRouter(prefix=this_page_routes)


@router.page("/{jwt_token}")
async def index(jwt_token: str):
    with BaseLayout().render(header=True, footer=True, args={"title": _("Share")}) as (header, footer):
        file_manager = globals.get_storage_manager()

        ui.label(jwt_token)

        with footer.inject():
            with ui.row().classes("w-full items-center"):
                ui.label("动态注入内容：").classes("text-white")
                ui.button("点击我!", color="red").classes("ml-4")
