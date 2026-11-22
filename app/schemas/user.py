"""Схемы пользователя: ввод, вывод, смена пароля.

ИЗМЕНЕНО 22.11.2026 (аудит/исправления):
  • email нормализуется в нижний регистр — иначе ``A@x.com`` и ``a@x.com``
    считались разными пользователями (регистрозависимая уникальность);
  • телефон валидируется по формату, а не только по длине;
  • пароль дополнительно требует букву и цифру (``12345678`` больше не
    проходит);
  • у ``UserCreate`` включён ``extra="forbid"``: попытка передать ``role``
    или ``is_active`` при регистрации теперь возвращает 422, а не молча
    игнорируется (защита от mass-assignment в глубину);
  • добавлена ``UserAdminUpdate`` — отдельная схема для админского PATCH
    (роль/is_active), чтобы обычный пользователь не мог их менять;
  • ``UserMe`` наследует ``UserBase`` и теперь гарантированно отдаёт
    нормализованные email/phone.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from app.models.enums import UserRole

_PHONE_RE = re.compile(r"^\+?[0-9][0-9\s\-()]{4,19}$")
_HAS_LETTER_RE = re.compile(r"[A-Za-zА-Яа-я]")
_HAS_DIGIT_RE = re.compile(r"\d")


def normalize_phone(value: str) -> str:
    value = value.strip()
    if not _PHONE_RE.match(value):
        raise ValueError(
            "phone must contain only digits, spaces, '-', '()' and "
            "an optional leading '+'"
        )
    return value


def _normalize_email(value: str) -> str:
    # Приводим к нижнему регистру целиком: для входа/уникальности это
    # ожидаемое поведение, а EmailStr уже проверил формат.
    return str(value).strip().lower()


def _validate_password_strength(value: str) -> str:
    if not _HAS_LETTER_RE.search(value) or not _HAS_DIGIT_RE.search(value):
        raise ValueError(
            "password must contain at least one letter and one digit"
        )
    return value


# ─────────── Базовые поля ───────────
class UserBase(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    phone: str = Field(..., min_length=5, max_length=20)

    @field_validator("full_name")
    @classmethod
    def _strip_full_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("full_name must not be blank")
        return v

    @field_validator("email")
    @classmethod
    def _lower_email(cls, v: EmailStr) -> str:
        return _normalize_email(str(v))

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, v: str) -> str:
        return normalize_phone(v)


# ─────────── Ввод ───────────
class UserCreate(UserBase):
    """Регистрация нового пользователя.

    role/is_active здесь намеренно отсутствуют: новый пользователь всегда
    создаётся клиентом (см. app/crud/user.py::create_user).
    """

    model_config = ConfigDict(extra="forbid")

    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        return _validate_password_strength(v)


class UserUpdate(BaseModel):
    """Обновление своего профиля. Все поля опциональны."""

    model_config = ConfigDict(extra="forbid")

    full_name: Optional[str] = Field(
        default=None, min_length=1, max_length=255
    )
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(
        default=None, min_length=5, max_length=20
    )

    @field_validator("full_name")
    @classmethod
    def _strip_full_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("full_name must not be blank")
        return v

    @field_validator("email")
    @classmethod
    def _lower_email(cls, v: Optional[EmailStr]) -> Optional[str]:
        return None if v is None else _normalize_email(str(v))

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, v: Optional[str]) -> Optional[str]:
        return None if v is None else normalize_phone(v)


class UserAdminUpdate(UserUpdate):
    """Админское обновление: профиль + роль + блокировка.

    ДОБАВЛЕНО: раньше не было способа назначить администратора или
    заблокировать пользователя через API.
    """

    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class PasswordChange(BaseModel):
    """Смена пароля. Требует текущий пароль для подтверждения."""

    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(..., min_length=8, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        return _validate_password_strength(v)

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


class AppointmentClient(BaseModel):
    """Контакт клиента для карточки записи.

    ДОБАВЛЕНО: владельцу салона и мастеру нужен телефон клиента, чтобы
    позвонить. Раньше вложенный ``UserPublic`` не содержал контактов вовсе.
    Схема используется только внутри ``AppointmentRead``, доступ к которому
    уже проверен по правам.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    phone: str


__all__ = [
    "AppointmentClient",
    "PasswordChange",
    "UserAdminUpdate",
    "UserBase",
    "UserCreate",
    "UserMe",
    "UserPublic",
    "UserUpdate",
    "normalize_phone",
]
