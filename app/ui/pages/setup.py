"""One-time browser setup. Credentials are accepted only in a bounded POST body."""

import hashlib
import hmac
import secrets
import time
from html import escape
from urllib.parse import parse_qs

from fastapi import APIRouter, Request
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import HTMLResponse, RedirectResponse

from app import globals
from app.config import settings
from app.core.i18n import _

router = APIRouter(prefix="/login/setup")
COOKIE = "stardrive_setup_csrf"
PATH = "/login/setup/"
HEADERS = {
    "Cache-Control": "no-store",
    # Chromium sends Origin: null for form POSTs under no-referrer. Keep the
    # origin on same-origin submissions while suppressing cross-origin referrers.
    "Referrer-Policy": "same-origin",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
}


def _signature(value: str) -> str:
    return hmac.new(
        settings.APP_SECRET.encode(),
        ("initial-setup:" + value).encode(),
        hashlib.sha256,
    ).hexdigest()


def _csrf_valid(value: str) -> bool:
    try:
        timestamp, nonce, signature = value.split(".")
        return (
            0 <= time.time() - int(timestamp) <= 1800
            and len(nonce) == 64
            and hmac.compare_digest(
                signature.encode("utf-8"),
                _signature(f"{timestamp}.{nonce}").encode("ascii"),
            )
        )
    except (ValueError, OverflowError):
        return False


def _page(request: Request, error: str = "", status: int = 200):
    token = settings.APP_SETUP_TOKEN
    enabled = bool(token and len(token.get_secret_value()) >= 32)
    title = escape(_("Create the first administrator"))
    content = f'<h1>{title}</h1><p role="alert">{escape(error)}</p>'
    csrf = f"{int(time.time())}.{secrets.token_hex(32)}"
    csrf += "." + _signature(csrf)
    if enabled:
        content += f'<form method="post" action="{PATH}"><input type="hidden" name="csrf" value="{csrf}">'
        for name, label, kind in (
            ("setup_token", _("Setup credential"), "password"),
            ("email", _("Email"), "email"),
            ("password", _("Password"), "password"),
            ("confirmation", _("Confirm password"), "password"),
        ):
            autocomplete = "username" if name == "email" else "new-password"
            content += f'<label>{escape(label)}<input name="{name}" type="{kind}" autocomplete="{autocomplete}" required maxlength="1024"></label>'
        content += (
            f'<button type="submit">{escape(_("Create administrator"))}</button></form>'
        )
        content += f'<p>{escape(_("Use at least 8 characters with uppercase, lowercase, a digit and a special character; at most 72 UTF-8 bytes."))}</p>'
    else:
        content += f'<p>{escape(_("Set STARDRIVE_APP_SETUP_TOKEN to a random credential of at least 32 characters in the deployment environment, then restart. Setup remains closed until configured."))}</p>'
    response = HTMLResponse(
        '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{title}</title><style>body{{font:1rem system-ui;max-width:28rem;margin:4rem auto;padding:1rem}}label,input{{display:block;width:100%;box-sizing:border-box}}input,button{{padding:.7rem;margin:.5rem 0 1rem}}</style>"
        f"</head><body>{content}</body></html>",
        status_code=status,
        headers=HEADERS,
    )
    response.set_cookie(
        COOKIE,
        csrf,
        max_age=1800,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
        path=PATH,
    )
    return response


@router.get("/")
async def setup_page(request: Request):
    if not await globals.get_user_manager().setup_required():
        return RedirectResponse("/login/", status_code=303, headers=HEADERS)
    return _page(request)


@router.post("/")
async def submit_setup(request: Request):
    # Require the browser's same-origin form POST, plus a signed, expiring
    # double-submit token. Never trust forwarded headers supplied by a client.
    if (
        request.headers.get("origin") != str(request.base_url).rstrip("/")
        or request.headers.get("sec-fetch-site") not in (None, "same-origin")
        or request.headers.get("content-type", "").split(";")[0]
        != "application/x-www-form-urlencoded"
    ):
        return _page(request, _("Setup request rejected. Reload and try again."), 403)
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 8192:
            return _page(
                request, _("Setup request rejected. Reload and try again."), 413
            )
        body.extend(chunk)
    try:
        fields = parse_qs(
            body.decode("utf-8"), keep_blank_values=True, max_num_fields=5
        )
        if set(fields) != {
            "csrf",
            "setup_token",
            "email",
            "password",
            "confirmation",
        } or any(len(v) != 1 for v in fields.values()):
            raise ValueError
        values = {k: v[0] for k, v in fields.items()}
        csrf = values.pop("csrf")
        if not _csrf_valid(csrf) or not secrets.compare_digest(
            csrf.encode(), request.cookies.get(COOKIE, "").encode()
        ):
            raise ValueError
    except (ValueError, UnicodeError):
        return _page(request, _("Setup request rejected. Reload and try again."), 403)
    try:
        await globals.get_user_manager().complete_setup(**values)
    except ValueError as exc:
        return _page(request, str(exc), 400)
    except SQLAlchemyError:
        return _page(request, _("Setup could not be saved. Reload and try again."), 503)
    response = RedirectResponse("/login/", status_code=303, headers=HEADERS)
    response.delete_cookie(COOKIE, path=PATH)
    return response
