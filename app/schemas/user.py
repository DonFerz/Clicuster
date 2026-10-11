"""Схемы пользователя: ввод, вывод, смена пароля.
"""


from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models.enums import UserRole


# ─────────── Базовые поля ───────────
class UserBase(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    phone: str = Field(..., min_length=5, max_length=20)


# ─────────── Ввод ───────────
class UserCreate(UserBase):
    """Регистрация нового пользователя."""

    password: str = Field(..., min_length=8, max_length=128)


class UserUpdate(BaseModel):
    """Обновление профиля. Все поля опциональны."""

    model_config = ConfigDict(extra="forbid")

    full_name: Optional[str] = Field(
        default=None, min_length=1, max_length=255
    )
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(
        default=None, min_length=5, max_length=20
    )


class PasswordChange(BaseModel):
    """Смена пароля. Требует текущий пароль для подтверждения."""

    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(..., min_length=8, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)

    @model_validator(mode="after")
    def check_passwords_differ(self) -> "PasswordChange":
        if self.new_password == self.current_password:
            raise ValueError(
                "New password must differ from the current one"
            )
        return self


# ─────────── Вывод ───────────
class UserPublic(BaseModel):
    """Публичная информация о пользователе.
    Видна всем (например, GET /users/{id}).
    Без email и phone — они доступны только владельцу (UserMe)
    или в специализированных контекстах (например, мастеру
    в его записи — через отдельную схему).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    role: UserRole


class UserMe(UserBase):
    """Полная информация о пользователе.
    Только для самого пользователя (GET /users/me).
    Содержит email, phone и служебные поля.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime


__all__ = [
    "PasswordChange",
    "UserBase",
    "UserCreate",
    "UserMe",
    "UserPublic",
    "UserUpdate",
]
