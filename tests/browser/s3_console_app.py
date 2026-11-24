"""Loopback-only synthetic application fixture for the opt-in browser suite."""

import asyncio
import os
from pathlib import Path

from app.bootstrap.env import setup_environment

setup_environment()
from fastapi import HTTPException, Request
from nicegui import app, ui
from app import globals
from app.bootstrap.app import create_app
from app.config import settings
from app.crud.user_crud import UserCRUD
from app.services.file_service import get_user_storage_root
from app.services.local_db_service import get_db_context
from app.services.storage_config_service import storage_config

create_app()
ready = False


def authorize(request):
    if request.headers.get("x-fixture-key") != os.environ["FIXTURE_KEY"]:
        raise HTTPException(403)


@app.on_startup
async def seed():
    global ready
    for _ in range(200):
        try:
            manager = globals.get_user_manager()
            break
        except RuntimeError:
            await asyncio.sleep(0.05)
    else:
        raise RuntimeError("Application startup did not complete")
    async with get_db_context() as session:
        for name in ("admin", "other"):
            email = f"browser-{name}@example.com"
            user = await UserCRUD.get_by_email(session, email)
            if user is None:
                user = await UserCRUD.create(
                    session,
                    email=email,
                    password=os.environ["FIXTURE_PASSWORD"],
                    is_superuser=name == "admin",
                    quota_bytes=10485760,
                )
                root = get_user_storage_root(user.id)
                (root / "original.txt").write_bytes(f"original-{name}".encode())
    await manager.initialize()
    ready = True


@app.get("/api/fixture/state")
async def state(request: Request):
    authorize(request)
    if not ready:
        return {"ready": False, "active": None, "profiles": []}
    profiles = await storage_config.list_profiles()
    return {
        "ready": ready,
        "active": storage_config.current_backend,
        "profiles": [
            {
                "id": p.id,
                "name": p.name,
                "active": p.is_active,
                "tested": p.last_test_success,
            }
            for p in profiles
        ],
    }


@app.post("/api/fixture/user")
async def user_status(request: Request, payload: dict):
    authorize(request)
    async with get_db_context() as session:
        user = await UserCRUD.get_by_email(session, "browser-admin@example.com")
        if "admin" in payload:
            await UserCRUD.update_superuser(
                session, user=user, is_superuser=payload["admin"]
            )
        if "active" in payload:
            await UserCRUD.update_status(
                session, user=user, is_active=payload["active"]
            )
    return {"ok": True}


ui.run(
    host="127.0.0.1",
    port=int(os.environ["FIXTURE_PORT"]),
    show=False,
    reload=False,
    storage_secret=settings.APP_SECRET,
    language="en-US",
    reconnect_timeout=settings.NICEGUI_RECONNECT_TIMEOUT,
    show_welcome_message=False,
)
