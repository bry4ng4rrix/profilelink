from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import AfterValidator, BaseModel, EmailStr, StringConstraints, model_validator

from app.core.usernames import USERNAME_PATTERN

Email = Annotated[EmailStr, AfterValidator(str.lower)]
Username = Annotated[
    str, StringConstraints(strip_whitespace=True, to_lower=True, pattern=USERNAME_PATTERN)
]


class RegisterIn(BaseModel):
    email: Email
    password: Annotated[str, StringConstraints(min_length=10, max_length=128)]
    password_confirm: str
    username: Username

    @model_validator(mode="after")
    def passwords_match(self) -> Self:
        if self.password != self.password_confirm:
            raise ValueError("passwords_mismatch")
        return self


class LoginIn(BaseModel):
    email: Email
    password: Annotated[str, StringConstraints(max_length=128)]


class MeOut(BaseModel):
    id: UUID
    email: str
    username: str
    session_expires_at: datetime
