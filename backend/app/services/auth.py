from datetime import datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.core.security import (
    DUMMY_HASH,
    hash_password,
    hash_token,
    new_session_token,
    verify_password,
)
from app.core.usernames import ensure_allowed
from app.models import AuthSession, Profile, User
from app.repositories import sessions, users
from app.schemas.auth import LoginIn, MeOut, RegisterIn

SESSION_LIFETIME = timedelta(days=14)


def _open_session(db: AsyncSession, user_id: UUID) -> tuple[str, datetime]:
    token = new_session_token()
    expires_at = utcnow() + SESSION_LIFETIME
    sessions.add(db, user_id, hash_token(token), expires_at)
    return token, expires_at


async def me(db: AsyncSession, session: AuthSession) -> MeOut:
    return await _identity(db, session.user_id, session.expires_at)


async def _identity(db: AsyncSession, user_id: UUID, expires_at: datetime) -> MeOut:
    row = await users.get_identity(db, user_id)
    return MeOut(id=row.id, email=row.email, username=row.username, session_expires_at=expires_at)


async def register(db: AsyncSession, data: RegisterIn) -> tuple[MeOut, str, datetime]:
    ensure_allowed(data.username)
    # Argon2 is CPU-bound and would stall every other request on the event loop.
    password_hash = await run_in_threadpool(hash_password, data.password)
    user = User(email=data.email, password_hash=password_hash)
    db.add(user)
    try:
        await db.flush()
        db.add(Profile(user_id=user.id, username=data.username))
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        taken = "email_taken" if "uq_users_email" in str(exc.orig) else "username_taken"
        raise HTTPException(409, taken) from exc
    token, expires_at = _open_session(db, user.id)
    await db.commit()
    return await _identity(db, user.id, expires_at), token, expires_at


async def login(db: AsyncSession, data: LoginIn) -> tuple[MeOut, str, datetime]:
    user = await users.get_by_email(db, data.email)
    # Unknown emails still pay for a hash, so timing does not reveal which accounts exist.
    valid = await run_in_threadpool(
        verify_password, user.password_hash if user else DUMMY_HASH, data.password
    )
    if not (user and valid and user.is_active):
        raise HTTPException(401, "invalid_credentials")
    await sessions.purge_expired(db)
    token, expires_at = _open_session(db, user.id)
    await db.commit()
    return await _identity(db, user.id, expires_at), token, expires_at


async def logout(db: AsyncSession, session: AuthSession) -> None:
    await db.delete(session)
    await db.commit()


async def refresh(db: AsyncSession, session: AuthSession) -> tuple[MeOut, str, datetime]:
    user_id = session.user_id
    await db.delete(session)
    token, expires_at = _open_session(db, user_id)
    await db.commit()
    return await _identity(db, user_id, expires_at), token, expires_at
