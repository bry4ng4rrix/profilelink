"""HTML page that creates an administrator, served by FastAPI and absent from the site.

Every account here is an administrator who can rewrite every destination, so the page needs a
secret code, and without one configured it does not exist. It stays useful in production, where
/docs is disabled.
"""

import logging
from html import escape
from typing import Annotated

from fastapi import APIRouter, Depends, Form, status
from fastapi.responses import HTMLResponse

from app.api.deps import require_registration_enabled
from app.core.config import settings
from app.services.admins import (
    MIN_PASSWORD_LENGTH,
    AdminError,
    create_admin,
    registration_code_matches,
)

logger = logging.getLogger(__name__)

_HEADERS = {
    "Cache-Control": "no-store",
    "X-Robots-Tag": "noindex, nofollow",
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
        "frame-ancestors 'none'; base-uri 'none'"
    ),
}

_STYLE = """
body{margin:0;min-height:100vh;display:grid;place-items:center;padding:24px;box-sizing:border-box;
background:#edf1ee;color:#12302b;font:16px/1.5 system-ui,sans-serif}
main{width:100%;max-width:380px;background:#fff;border-radius:20px;padding:28px;box-sizing:border-box}
h1{margin:0 0 20px;font-size:26px}
label{display:block;margin-top:14px;font-size:14px;font-weight:600}
input{width:100%;box-sizing:border-box;height:44px;margin-top:6px;padding:0 12px;font:inherit;
border:1px solid #bccac2;border-radius:10px}
button{width:100%;height:46px;margin-top:22px;border:0;border-radius:12px;background:#0e6b5c;
color:#fff;font:inherit;font-weight:600;cursor:pointer}
.error{margin:0 0 8px;padding:10px 12px;border-radius:10px;background:#c2264d1a;color:#c2264d}
a{color:#0e6b5c}
"""


def _page(title: str, content: str, status_code: int) -> HTMLResponse:
    html = (
        f'<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{title}</title><style>{_STYLE}</style></head>"
        f"<body><main><h1>{title}</h1>{content}</main></body></html>"
    )
    return HTMLResponse(html, status_code=status_code, headers=_HEADERS)


def _form(error: str | None = None, status_code: int = status.HTTP_200_OK) -> HTMLResponse:
    notice = f'<p class="error" role="alert">{escape(error)}</p>' if error else ""
    return _page(
        "Créer un administrateur",
        f"""{notice}<form method="post" autocomplete="off">
        <label>Email<input type="email" name="email" required autocomplete="username"></label>
        <label>Mot de passe ({MIN_PASSWORD_LENGTH} caractères minimum)
          <input type="password" name="password" required minlength="{MIN_PASSWORD_LENGTH}"
                 autocomplete="new-password"></label>
        <label>Confirmez le mot de passe
          <input type="password" name="password_confirm" required autocomplete="new-password"></label>
        <label>Code d'inscription
          <input type="password" name="registration_code" required autocomplete="off"></label>
        <button type="submit">Créer le compte</button>
        </form>""",
        status_code,
    )


router = APIRouter(include_in_schema=False, dependencies=[Depends(require_registration_enabled)])


@router.get("/register")
async def register_page() -> HTMLResponse:
    return _form()


@router.post("/register")
async def register(
    email: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
    password_confirm: Annotated[str, Form()] = "",
    registration_code: Annotated[str, Form()] = "",
) -> HTMLResponse:
    if not registration_code_matches(registration_code):
        logger.warning("admin_registration_refused")
        return _form("Code d'inscription incorrect.", status.HTTP_403_FORBIDDEN)
    if password != password_confirm:
        return _form(
            "Les deux mots de passe ne correspondent pas.",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    try:
        await create_admin(email, password)
    except AdminError as exc:
        return _form(str(exc), status.HTTP_422_UNPROCESSABLE_CONTENT)

    logger.warning("admin_registered", extra={"email": email.lower()})
    login_url = escape(f"{settings.frontend_origin}/login")
    return _page(
        "Compte créé",
        f'<p>Vous pouvez maintenant <a href="{login_url}">vous connecter</a>.</p>',
        status.HTTP_201_CREATED,
    )
