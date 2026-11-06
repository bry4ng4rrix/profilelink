import pytest
from fastapi.routing import APIRoute

from app.core.config import settings
from app.main import app
from tests.conftest import add_link, _client

SECRET_HOST = "secret-destination.example.com"
SECRET_URL = f"https://{SECRET_HOST}/private"


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
    return (
        path.replace("{username}", "bryan")
        .replace("{link_id}", "00000000-0000-0000-0000-000000000000")
    )


def test_every_documented_route_is_discovered():
    paths = {route.path for route in http_routes()}

    assert "/api/v1/owner/profile" in paths
    assert "/r/{username}" in paths
    assert len(paths) >= 18


def owner_routes() -> list[tuple[str, str]]:
    return [
        (method, route.path)
        for route in http_routes()
        if route.path.startswith("/api/v1/owner")
        for method in route.methods
    ]


async def test_route_list_covers_owner_endpoints():
    assert len(owner_routes()) == 12


async def test_no_public_route_reveals_private_data(owner, visitor):
    await add_link(owner, SECRET_URL)
    public = [r for r in http_routes() if "/owner" not in r.path and "/auth" not in r.path]
    assert len(public) >= 4

    for route in public:
        for method in route.methods:
            response = await visitor.request(method, fill(route.path))
            body = response.text.lower()
            assert SECRET_HOST not in body, route.path
            assert "destination_url" not in body, route.path
            assert "bryan@example.com" not in body, route.path
            assert "password" not in body, route.path
            if route.path != "/r/{username}":
                assert SECRET_HOST not in str(response.headers), route.path


async def test_destination_only_leaves_through_the_redirect_location(owner, visitor):
    await add_link(owner, SECRET_URL)

    response = await visitor.get("/r/bryan")

    assert response.headers["location"] == SECRET_URL
    assert SECRET_HOST not in response.text


async def test_visitors_never_need_an_origin_or_cookie(owner, visitor):
    await add_link(owner)

    assert (await visitor.get("/api/v1/public/profiles/bryan")).status_code == 200
    assert (await visitor.post("/api/v1/public/profiles/bryan/visit")).status_code == 204
    assert (await visitor.get("/r/bryan")).status_code == 302


@pytest.mark.parametrize("method,path", owner_routes())
async def test_owner_routes_refuse_anonymous_requests(anonymous, method, path):
    response = await anonymous.request(method, fill(path), json={})

    assert response.status_code == 401, path


@pytest.mark.parametrize("method,path", owner_routes())
async def test_owner_routes_refuse_a_forged_cookie(anonymous, method, path):
    anonymous.cookies.set("pl_session", "forged-token")

    assert (await anonymous.request(method, fill(path), json={})).status_code == 401


async def test_auth_routes_refuse_anonymous_requests(anonymous):
    assert (await anonymous.get("/api/v1/auth/me")).status_code == 401
    assert (await anonymous.post("/api/v1/auth/logout")).status_code == 401
    assert (await anonymous.post("/api/v1/auth/refresh")).status_code == 401


async def test_owners_cannot_touch_each_others_links(owner_factory, visitor):
    alice = await owner_factory("alice")
    mallory = await owner_factory("mallory")
    link = await add_link(alice, "https://alice.example.com/")
    path = f"/api/v1/owner/links/{link['id']}"

    assert (await mallory.put(path, json={"destination_url": "https://evil.test/"})).status_code == 404
    assert (await mallory.delete(path)).status_code == 404
    assert (await mallory.patch(f"{path}/status", json={"is_active": False})).status_code == 404

    assert (await mallory.get("/api/v1/owner/links")).json() == []
    assert (await visitor.get("/r/alice")).headers["location"] == "https://alice.example.com/"


async def test_owner_endpoints_only_ever_act_on_the_session_owner(owner_factory):
    alice = await owner_factory("alice")
    mallory = await owner_factory("mallory")

    await mallory.put(
        "/api/v1/owner/profile",
        json={"username": "mallory", "id": "x", "user_id": "x", "bio": "changed"},
    )

    assert (await alice.get("/api/v1/owner/profile")).json()["bio"] is None


async def test_analytics_are_isolated(owner_factory, visitor):
    alice = await owner_factory("alice")
    mallory = await owner_factory("mallory")
    await add_link(alice)
    await visitor.get("/r/alice")

    overview = (await mallory.get("/api/v1/owner/analytics/overview")).json()

    assert overview["total_clicks"] == 0


@pytest.mark.parametrize(
    "headers", [{}, {"Origin": "https://evil.test"}, {"Origin": "https://profil.test.evil.test"}]
)
async def test_state_changing_requests_need_the_allowed_origin(owner, headers):
    token = owner.cookies["pl_session"]
    async with _client() as client:
        client.headers.pop("origin")
        client.cookies.set("pl_session", token)

        for method, path in [
            ("PUT", "/api/v1/owner/profile"),
            ("PATCH", "/api/v1/owner/profile/status"),
            ("POST", "/api/v1/owner/links"),
            ("POST", "/api/v1/auth/logout"),
            ("POST", "/api/v1/auth/login"),
        ]:
            response = await client.request(method, path, json={}, headers=headers)
            assert response.status_code == 403, path
            assert response.json()["detail"] == "origin_not_allowed"


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


async def test_production_cookie_is_secure_and_domain_scoped(owner, monkeypatch):
    from app.api import auth as auth_api

    monkeypatch.setattr(type(settings), "is_production", property(lambda self: True))
    monkeypatch.setattr(settings, "cookie_domain", "profil.test")

    scope = auth_api._cookie_scope()

    assert scope["secure"] is True
    assert scope["httponly"] is True
    assert scope["samesite"] == "lax"
    assert scope["domain"] == "profil.test"
