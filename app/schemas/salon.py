"""Схемы салона.

ИЗМЕНЕНО 22.11.2026 (аудит/исправления):
  • названия/адреса обрезаются по краям, пустое название запрещено;
  • телефон валидируется тем же правилом, что и у пользователя;
  • ``SalonCreate``/``SalonUpdate`` запрещают лишние поля (``extra="forbid"``),
    чтобы нельзя было передать ``owner_id``/``is_active`` при создании;
  • добавлена документированная связь с ``UserPublic`` (владелец).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import SalonType
from app.schemas.user import UserPublic, normalize_phone


class SalonBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    address: Optional[str] = Field(default=None, max_length=500)
    phone: Optional[str] = Field(default=None, max_length=20)
    type: SalonType

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v

    @field_validator("address")
    @classmethod
    def _strip_address(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        return v or None

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, v: Optional[str]) -> Optional[str]:
        return None if v is None else normalize_phone(v)


class SalonCreate(SalonBase):
    model_config = ConfigDict(extra="forbid")


class SalonUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    address: Optional[str] = Field(default=None, max_length=500)
    phone: Optional[str] = Field(default=None, max_length=20)
    type: Optional[SalonType] = None
    is_active: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, v: Optional[str]) -> Optional[str]:
        return None if v is None else normalize_phone(v)


class SalonRead(SalonBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    owner: UserPublic


__all__ = ["SalonBase", "SalonCreate", "SalonRead", "SalonUpdate"]
