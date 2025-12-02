#!/usr/bin/env python3
"""This is just a simple authentication example.

Please see the `OAuth2 example at FastAPI <https://fastapi.tiangolo.com/tutorial/security/simple-oauth2/>`_  or
use the great `Authlib package <https://docs.authlib.org/en/v0.13/client/starlette.html#using-fastapi>`_ to implement a classing real authentication system.
Here we just demonstrate the NiceGUI integration.
"""
from typing import Optional

from fastapi.responses import RedirectResponse
from nicegui import app, ui, APIRouter

router = APIRouter(prefix="/login")

# in reality users passwords would obviously need to be hashed
passwords = {"user1": "pass1", "user2": "pass2"}

unrestricted_page_routes = {"/login"}


# @app.add_middleware
# class AuthMiddleware(BaseHTTPMiddleware):
#     """This middleware restricts access to all NiceGUI pages.
#
#     It redirects the user to the login page if they are not authenticated.
#     """
#
#     async def dispatch(self, request: Request, call_next):
#         if not app.storage.user.get('authenticated', False):
#             if not request.url.path.startswith('/_nicegui') and request.url.path not in unrestricted_page_routes:
#                 return RedirectResponse(f'/login?redirect_to={request.url.path}')
#         return await call_next(request)


@router.page("/")
def login(redirect_to: str = "/login") -> Optional[RedirectResponse]:
    def try_login() -> (
        None
    ):  # local function to avoid passing username and password as arguments
        if passwords.get(username.value) == password.value:
            app.storage.user.update({"username": username.value, "authenticated": True})
            ui.navigate.to(redirect_to)  # go back to where the user wanted to go
        else:
            ui.notify("Wrong username or password", color="negative")

    if app.storage.user.get("authenticated", False):
        return RedirectResponse("/login")

    with ui.card().classes("absolute-center"):
        username = ui.input("Username").on("keydown.enter", try_login)
        password = ui.input("Password", password=True, password_toggle_button=True).on(
            "keydown.enter", try_login
        )
        ui.button("Log in", on_click=try_login)

    return None
