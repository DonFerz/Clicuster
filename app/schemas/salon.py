from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import SalonType
from app.schemas.user import UserPublic


class SalonBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    address: Optional[str] = Field(default=None, max_length=500)
    phone: Optional[str] = Field(default=None, max_length=20)
    type: SalonType


class SalonCreate(SalonBase):
    owner_id: int


class SalonUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    address: Optional[str] = Field(default=None, max_length=500)
    phone: Optional[str] = Field(default=None, max_length=20)
    type: Optional[SalonType] = None
    is_active: Optional[bool] = None


class SalonRead(SalonBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    owner: UserPublic
