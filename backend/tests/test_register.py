import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.core.config import Settings, settings
from app.core.db import SessionLocal
from app.main import app
from app.models import AuthSession, User, VaProfile
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD

TOKEN = "a-registration-token-of-sufficient-length"


def form(**overrides) -> dict:
    return {
        "email": "new.admin@example.com",
        "password": ADMIN_PASSWORD,
        "password_confirm": ADMIN_PASSWORD,
        "registration_code": TOKEN,
    } | overrides


async def accounts() -> list[str]:
    async with SessionLocal() as db:
        return list((await db.scalars(select(User.email))).all())


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "registration_token", TOKEN)


async def test_the_page_does_not_exist_without_a_token(visitor):
    assert (await visitor.get("/register")).status_code == 404
    response = await visitor.post("/register", data=form())
    assert response.status_code == 404
    assert await accounts() == []


async def test_the_html_page_stays_out_of_the_api_documentation():
    assert "/register" not in app.openapi()["paths"]


async def test_the_api_route_is_listed_with_the_auth_routes():
    route = app.openapi()["paths"]["/api/v1/auth/register"]["post"]

    assert route["tags"] == ["auth"]


async def test_the_page_shows_a_form_that_cannot_be_cached_or_indexed(visitor, enabled):
    response = await visitor.get("/register")

    assert response.status_code == 200
    assert 'name="registration_code"' in response.text
    assert response.headers["cache-control"] == "no-store"
    assert "noindex" in response.headers["x-robots-tag"]
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert TOKEN not in response.text


async def test_the_right_code_creates_an_admin_who_can_log_in(visitor, anonymous, enabled):
    response = await visitor.post("/register", data=form(email="New.Admin@Example.com"))

    assert response.status_code == 201
    assert f"{settings.frontend_origin}/login" in response.text
    assert await accounts() == ["new.admin@example.com"]

    login = await anonymous.post(
        "/api/v1/auth/login", json={"email": "new.admin@example.com", "password": ADMIN_PASSWORD}
    )
    assert login.status_code == 200


async def test_each_new_admin_leaves_a_trace_without_the_secrets(visitor, enabled, caplog):
    await visitor.post("/register", data=form())

    assert "admin_registered" in caplog.text
    assert TOKEN not in caplog.text and ADMIN_PASSWORD not in caplog.text


async def test_registering_opens_no_session(visitor, enabled):
    response = await visitor.post("/register", data=form())

    assert "set-cookie" not in response.headers
    async with SessionLocal() as db:
        assert await db.scalar(select(AuthSession)) is None


async def test_the_password_is_stored_as_argon2id(visitor, enabled):
    await visitor.post("/register", data=form())

    async with SessionLocal() as db:
        assert (await db.scalar(select(User.password_hash))).startswith("$argon2id$")


@pytest.mark.parametrize("code", ["", "wrong", TOKEN[:-1], TOKEN + "x", TOKEN.upper()])
async def test_a_wrong_code_creates_nothing(visitor, enabled, code):
    response = await visitor.post("/register", data=form(registration_code=code))

    assert response.status_code == 403
    assert "Code d'inscription incorrect." in response.text.replace("&#x27;", "'")
    assert await accounts() == []


async def test_the_code_is_checked_before_anything_else(visitor, enabled):
    response = await visitor.post(
        "/register", data=form(registration_code="wrong", email="not-an-email", password="x")
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    "overrides",
    [
        {"email": "not-an-email"},
        {"password": "short", "password_confirm": "short"},
        {"password": "x" * 129, "password_confirm": "x" * 129},
        {"password_confirm": "something-else-entirely"},
    ],
)
async def test_invalid_input_is_refused(visitor, enabled, overrides):
    response = await visitor.post("/register", data=form(**overrides))

    assert response.status_code == 422
    assert await accounts() == []


async def test_an_existing_account_is_refused(admin, visitor, enabled):
    response = await visitor.post("/register", data=form(email=ADMIN_EMAIL))

    assert response.status_code == 422
    assert "existe déjà" in response.text
    assert await accounts() == [ADMIN_EMAIL]


async def test_user_input_is_escaped(visitor, enabled):
    response = await visitor.post("/register", data=form(email="<script>alert(1)</script>"))

    assert "<script>" not in response.text
    assert "&lt;script&gt;" in response.text


async def test_it_cannot_create_a_va(visitor, enabled):
    await visitor.post("/register", data=form())

    async with SessionLocal() as db:
        assert await db.scalar(select(VaProfile)) is None


@pytest.mark.parametrize("value", ["", None])
def test_an_empty_token_means_disabled(value):
    assert Settings(registration_token=value).registration_token is None


def test_a_weak_token_stops_the_application_from_starting():
    with pytest.raises(ValidationError, match="32 characters"):
        Settings(registration_token="too-short")


API_REGISTER = "/api/v1/auth/register"


def payload(**overrides) -> dict:
    return form(**overrides)


async def test_api_route_is_closed_without_a_token(anonymous):
    response = await anonymous.post(API_REGISTER, json=payload())

    assert response.status_code == 404
    assert await accounts() == []


async def test_api_route_creates_an_admin_who_can_log_in(anonymous, enabled):
    response = await anonymous.post(API_REGISTER, json=payload(email="New.Admin@Example.com"))

    assert response.status_code == 201
    assert response.json() == {"email": "new.admin@example.com"}
    assert "set-cookie" not in response.headers
    login = await anonymous.post(
        "/api/v1/auth/login", json={"email": "new.admin@example.com", "password": ADMIN_PASSWORD}
    )
    assert login.status_code == 200


@pytest.mark.parametrize("code", ["", "wrong", TOKEN[:-1], TOKEN + "x"])
async def test_api_route_refuses_a_wrong_code(anonymous, enabled, code):
    response = await anonymous.post(API_REGISTER, json=payload(registration_code=code))

    assert (response.status_code, response.json()["detail"]) == (403, "invalid_registration_code")
    assert await accounts() == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"email": "not-an-email"},
        {"password": "short", "password_confirm": "short"},
        {"password": "x" * 129, "password_confirm": "x" * 129},
        {"password_confirm": "something-else-entirely"},
    ],
)
async def test_api_route_refuses_invalid_input(anonymous, enabled, overrides):
    response = await anonymous.post(API_REGISTER, json=payload(**overrides))

    assert response.status_code == 422
    assert await accounts() == []


async def test_api_route_refuses_an_existing_account(admin, enabled):
    response = await admin.post(API_REGISTER, json=payload(email=ADMIN_EMAIL))

    assert (response.status_code, response.json()["detail"]) == (409, "email_taken")


async def test_api_route_cannot_be_reached_from_another_site(visitor, enabled):
    response = await visitor.post(
        API_REGISTER, json=payload(), headers={"Origin": "https://evil.test"}
    )

    assert (response.status_code, response.json()["detail"]) == (403, "origin_not_allowed")
    assert await accounts() == []


async def test_swagger_can_call_the_api_from_its_own_address(visitor, enabled):
    response = await visitor.post(
        API_REGISTER, json=payload(), headers={"Origin": "http://api.profil.test"}
    )

    assert response.status_code == 201
