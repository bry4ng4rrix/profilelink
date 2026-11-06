from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import AfterValidator, BaseModel, EmailStr, StringConstraints, model_validator

Email = Annotated[EmailStr, AfterValidator(str.lower)]


class LoginIn(BaseModel):
    email: Email
    password: Annotated[str, StringConstraints(max_length=128)]


class RegisterIn(BaseModel):
    email: Email
    password: Annotated[str, StringConstraints(min_length=12, max_length=128)]
    password_confirm: str
    registration_code: str

    @model_validator(mode="after")
    def passwords_match(self) -> Self:
        if self.password != self.password_confirm:
            raise ValueError("passwords_mismatch")
        return self


class RegisteredOut(BaseModel):
    email: str


class MeOut(BaseModel):
    id: UUID
    email: str
    session_expires_at: datetime
