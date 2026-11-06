"""Administrator accounts, shared by the command line and the unlisted registration page."""

import asyncio
import hmac

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models import AuthSession, User
from app.repositories import users
from app.schemas.auth import Email

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128


class AdminError(Exception):
    def __init__(self, message: str, code: str = "invalid_account") -> None:
        super().__init__(message)
        self.code = code


def registration_code_matches(code: str) -> bool:
    expected = settings.registration_token or ""
    return bool(expected) and hmac.compare_digest(code.encode(), expected.encode())


def _check_password(password: str) -> None:
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise AdminError(
            f"Le mot de passe doit contenir de {MIN_PASSWORD_LENGTH} à "
            f"{MAX_PASSWORD_LENGTH} caractères."
        )


def _clean_email(raw: str) -> str:
    try:
        return TypeAdapter(Email).validate_python(raw)
    except ValidationError as exc:
        raise AdminError(f"Adresse email invalide : {raw}") from exc


async def create_admin(raw_email: str, password: str) -> str:
    _check_password(password)
    email = _clean_email(raw_email)
    password_hash = await asyncio.to_thread(hash_password, password)
    async with SessionLocal() as db:
        db.add(User(email=email, password_hash=password_hash))
        try:
            await db.commit()
        except IntegrityError as exc:
            raise AdminError(f"Ce compte existe déjà : {email}", "email_taken") from exc
    return email


async def reset_password(raw_email: str, password: str) -> None:
    _check_password(password)
    email = _clean_email(raw_email)
    password_hash = await asyncio.to_thread(hash_password, password)
    async with SessionLocal() as db:
        user = await users.get_by_email(db, email)
        if user is None:
            raise AdminError(f"Aucun compte pour : {email}")
        user.password_hash = password_hash
        # A reset usually means a leaked password: every open session is closed.
        await db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
        await db.commit()
