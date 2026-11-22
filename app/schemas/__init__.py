"""Публичный API пакета `app.schemas`.

Здесь собраны все Pydantic-схемы проекта в одном месте.
Импорт из роутеров:

    from app.schemas import UserMe, UserPublic, UserCreate, TokenPair

ИЗМЕНЕНО 22.11.2026 (аудит/исправления): добавлены новые схемы
``AppointmentClient`` и ``UserAdminUpdate``.
"""

# ─────────── appointment ───────────
from app.schemas.appointment import (
    AppointmentBase,
    AppointmentCreate,
    AppointmentRead,
    AppointmentUpdate,
)

# ─────────── auth ───────────
from app.schemas.auth import (
    RefreshRequest,
    TokenPair,
    TokenPayload,
)

# ─────────── master ───────────
from app.schemas.master import (
    MasterBase,
    MasterCreate,
    MasterRead,
    MasterUpdate,
)

# ─────────── salon ───────────
from app.schemas.salon import (
    SalonBase,
    SalonCreate,
    SalonRead,
    SalonUpdate,
)

# ─────────── service ───────────
from app.schemas.service import (
    ServiceBase,
    ServiceCreate,
    ServiceRead,
    ServiceUpdate,
)

# ─────────── user ───────────
from app.schemas.user import (
    AppointmentClient,
    PasswordChange,
    UserAdminUpdate,
    UserBase,
    UserCreate,
    UserMe,
    UserPublic,
    UserUpdate,
)

__all__ = [
    # appointment
    "AppointmentBase",
    "AppointmentCreate",
    "AppointmentClient",
    "AppointmentRead",
    "AppointmentUpdate",
    # auth
    "RefreshRequest",
    "TokenPair",
    "TokenPayload",
    # master
    "MasterBase",
    "MasterCreate",
    "MasterRead",
    "MasterUpdate",
    # salon
    "SalonBase",
    "SalonCreate",
    "SalonRead",
    "SalonUpdate",
    # service
    "ServiceBase",
    "ServiceCreate",
    "ServiceRead",
    "ServiceUpdate",
    # user
    "PasswordChange",
    "UserAdminUpdate",
    "UserBase",
    "UserCreate",
    "UserMe",
    "UserPublic",
    "UserUpdate",
]
