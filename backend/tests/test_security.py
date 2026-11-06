import pytest
from fastapi.routing import APIRoute

from app.core.config import settings
from app.main import app
from tests.conftest import ADMIN_EMAIL, INSTAGRAM, client, create_va

SECRET_HOST = "secret-destination.example.com"
SECRET_URL = f"https://{SECRET_HOST}/private"
ZERO_ID = "00000000-0000-0000-0000-000000000000"


def http_routes() -> list[APIRoute]:
    def walk(routes):
        for route in routes:
            if isinstance(route, APIRoute):
                yield route
            nested = getattr(route, "routes", None) or getattr(
                getattr(route, "original_router", None), "routes", None
            )
            if nested:
                yield from walk(nested)

    return list(walk(app.routes))


def fill(path: str) -> str:
    return path.replace("{username}", "bryan").replace("{va_id}", ZERO_ID)


def admin_routes() -> list[tuple[str, str]]:
    return sorted(
        (method, route.path)
        for route in http_routes()
        if route.path.startswith("/api/v1/admin")
        for method in route.methods
    )


def test_every_admin_endpoint_is_discovered():
    assert len(admin_routes()) == 12


def test_no_owner_route_remains():
    assert not [route.path for route in http_routes() if "owner" in route.path]


async def test_no_public_route_reveals_private_data(admin, visitor):
    await create_va(admin, destination_url=SECRET_URL)
    public = [r for r in http_routes() if "/admin" not in r.path and "/auth" not in r.path]
    assert len(public) >= 3

    for route in public:
        for method in route.methods:
            response = await visitor.request(method, fill(route.path))
            body = response.text.lower()
            assert SECRET_HOST not in body, route.path
            assert "destination" not in body, route.path
            assert ADMIN_EMAIL not in body, route.path
            assert INSTAGRAM.lower() not in body, route.path
            assert "instagram" not in body, route.path
            assert "password" not in body, route.path
            if route.path != "/r/{username}":
                assert SECRET_HOST not in str(response.headers), route.path


async def test_destination_only_leaves_through_the_redirect_location(admin, visitor):
    await create_va(admin, destination_url=SECRET_URL)

    response = await visitor.get("/r/bryan")

    assert response.headers["location"] == SECRET_URL
    assert SECRET_HOST not in response.text


async def test_destination_cannot_reach_a_public_code_path():
    from sqlalchemy.exc import InvalidRequestError

    from app.core.db import SessionLocal
    from app.models import VaProfile
    from sqlalchemy import select

    async with SessionLocal() as db:
        db.add(
            VaProfile(
                username="lazy",
                first_name="L",
                last_name="Z",
                age=30,
                instagram_url="https://instagram.com/lazy",
                photo_url="x",
            )
        )
        await db.commit()

    async with SessionLocal() as db:
        va = await db.scalar(select(VaProfile))
        with pytest.raises(InvalidRequestError):
            va.link  # noqa: B018


async def test_visitors_never_need_an_origin_or_cookie(admin, visitor):
    await create_va(admin)

    assert (await visitor.get("/api/v1/public/profiles/bryan")).status_code == 200
    assert (await visitor.post("/api/v1/public/profiles/bryan/visit")).status_code == 204
    assert (await visitor.get("/r/bryan")).status_code == 302


@pytest.mark.parametrize("method,path", admin_routes())
async def test_admin_routes_refuse_anonymous_requests(anonymous, method, path):
    assert (await anonymous.request(method, fill(path), json={})).status_code == 401


@pytest.mark.parametrize("method,path", admin_routes())
async def test_admin_routes_refuse_a_forged_cookie(anonymous, method, path):
    anonymous.cookies.set("pl_session", "forged-token")

    assert (await anonymous.request(method, fill(path), json={})).status_code == 401


async def test_auth_routes_refuse_anonymous_requests(anonymous):
    assert (await anonymous.get("/api/v1/auth/me")).status_code == 401
    assert (await anonymous.post("/api/v1/auth/logout")).status_code == 401
    assert (await anonymous.post("/api/v1/auth/refresh")).status_code == 401


async def test_a_visitor_can_modify_nothing(admin, visitor):
    va = await create_va(admin)
    path = f"/api/v1/admin/vas/{va['id']}"

    assert (await visitor.delete(path)).status_code == 403
    assert (await visitor.patch(f"{path}/status", json={"is_active": False})).status_code == 403

    assert (await admin.get(path)).json()["is_active"] is True


@pytest.mark.parametrize(
    "headers", [{}, {"Origin": "https://evil.test"}, {"Origin": "https://profil.test.evil.test"}]
)
async def test_state_changing_requests_need_the_allowed_origin(admin, headers):
    token = admin.cookies["pl_session"]
    async with client() as attacker:
        attacker.cookies.set("pl_session", token)

        for method, path in [
            ("POST", "/api/v1/admin/vas"),
            ("PUT", f"/api/v1/admin/vas/{ZERO_ID}"),
            ("DELETE", f"/api/v1/admin/vas/{ZERO_ID}"),
            ("PATCH", f"/api/v1/admin/vas/{ZERO_ID}/status"),
            ("PUT", f"/api/v1/admin/vas/{ZERO_ID}/link"),
            ("POST", "/api/v1/auth/logout"),
            ("POST", "/api/v1/auth/login"),
        ]:
            response = await attacker.request(method, path, json={}, headers=headers)
            assert response.status_code == 403, path
            assert response.json()["detail"] == "origin_not_allowed"


async def test_a_same_origin_request_is_accepted_but_a_lookalike_is_not(anonymous):
    login = {"email": "nobody@example.com", "password": "x"}

    same = await anonymous.post(
        "/api/v1/auth/login", json=login, headers={"Origin": "http://api.profil.test"}
    )
    other = await anonymous.post(
        "/api/v1/auth/login", json=login, headers={"Origin": "http://api.profil.test.evil.test"}
    )

    assert same.status_code == 401
    assert other.status_code == 403


async def test_cors_allows_only_the_configured_origin(visitor):
    allowed = await visitor.options(
        "/api/v1/auth/login",
        headers={
            "Origin": settings.frontend_origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    refused = await visitor.options(
        "/api/v1/auth/login",
        headers={"Origin": "https://evil.test", "Access-Control-Request-Method": "POST"},
    )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == settings.frontend_origin
    assert allowed.headers["access-control-allow-credentials"] == "true"
    assert "access-control-allow-origin" not in refused.headers


async def test_production_cookie_is_secure_and_domain_scoped(monkeypatch):
    from app.api import auth as auth_api

    monkeypatch.setattr(type(settings), "is_production", property(lambda self: True))
    monkeypatch.setattr(settings, "cookie_domain", "profil.test")

    scope = auth_api._cookie_scope()

    assert scope["secure"] is True
    assert scope["httponly"] is True
    assert scope["samesite"] == "lax"
    assert scope["domain"] == "profil.test"
