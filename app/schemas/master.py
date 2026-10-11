from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import MasterPosition
from app.schemas.user import UserPublic


class MasterBase(BaseModel):
    salon_id: int
    position: MasterPosition = MasterPosition.MASTER
    description: Optional[str] = Field(default=None, max_length=500)


class MasterCreate(MasterBase):
    full_name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    phone: str = Field(..., min_length=5, max_length=20)
    password: str = Field(..., min_length=8, max_length=128)


class MasterUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    salon_id: Optional[int] = None
    position: Optional[MasterPosition] = None
    description: Optional[str] = Field(default=None, max_length=500)
    is_active: Optional[bool] = None


class MasterRead(MasterBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    user: UserPublic
