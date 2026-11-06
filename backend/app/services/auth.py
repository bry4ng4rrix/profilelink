from datetime import datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.core.security import DUMMY_HASH, hash_token, new_session_token, verify_password
from app.models import AuthSession, User
from app.repositories import sessions, users
from app.schemas.auth import LoginIn, MeOut

SESSION_LIFETIME = timedelta(days=14)


def _open_session(db: AsyncSession, user_id: UUID) -> tuple[str, datetime]:
    token = new_session_token()
    expires_at = utcnow() + SESSION_LIFETIME
    sessions.add(db, user_id, hash_token(token), expires_at)
    return token, expires_at


async def me(db: AsyncSession, session: AuthSession) -> MeOut:
    user = await db.get(User, session.user_id)
    return MeOut(id=user.id, email=user.email, session_expires_at=session.expires_at)


async def login(db: AsyncSession, data: LoginIn) -> tuple[MeOut, str, datetime]:
    user = await users.get_by_email(db, data.email)
    # Unknown emails still pay for a hash, so timing does not reveal which accounts exist.
    # Argon2 is CPU-bound and would stall every other request on the event loop.
    valid = await run_in_threadpool(
        verify_password, user.password_hash if user else DUMMY_HASH, data.password
    )
    if not (user and valid and user.is_active):
        raise HTTPException(401, "invalid_credentials")
    await sessions.purge_expired(db)
    token, expires_at = _open_session(db, user.id)
    await db.commit()
    return MeOut(id=user.id, email=user.email, session_expires_at=expires_at), token, expires_at


async def logout(db: AsyncSession, session: AuthSession) -> None:
    await db.delete(session)
    await db.commit()


async def refresh(db: AsyncSession, session: AuthSession) -> tuple[MeOut, str, datetime]:
    user = await db.get(User, session.user_id)
    await db.delete(session)
    token, expires_at = _open_session(db, user.id)
    await db.commit()
    return MeOut(id=user.id, email=user.email, session_expires_at=expires_at), token, expires_at
