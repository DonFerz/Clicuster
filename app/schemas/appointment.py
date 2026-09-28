from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import RecordStatus
from app.schemas.master import MasterRead
from app.schemas.service import ServiceRead
from app.schemas.user import UserRead


class AppointmentBase(BaseModel):
    start_time: datetime
    end_time: datetime
    master_id: int
    client_id: int
    service_id: int
    comment: Optional[str] = Field(None, max_length=500)


class AppointmentCreate(AppointmentBase):
    pass


class AppointmentUpdate(BaseModel):
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    master_id: Optional[int] = None
    service_id: Optional[int] = None
    status: Optional[RecordStatus] = None
    comment: Optional[str] = Field(None, max_length=500)


class AppointmentRead(AppointmentBase):
    id: int
    status: RecordStatus
    created_at: datetime
    updated_at: datetime

    master: MasterRead
    client: UserRead
    service: ServiceRead

    model_config = ConfigDict(from_attributes=True)
