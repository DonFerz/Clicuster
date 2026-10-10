"""Публичный API пакета `app.dependencies`.

Все FastAPI-зависимости в одном месте.
Роутеры импортируют их одной строкой:
    from app.dependencies import CurrentUser, DbSession, PaginationDep
"""

from app.dependencies.auth import (
    CurrentUser,
    get_current_active_user,
    get_current_user,
    oauth2_scheme,
    require_role,
)
from app.dependencies.db import DbSession, get_db
from app.dependencies.pagination import MAX_LIMIT, Pagination, PaginationDep
from app.dependencies.redis import RedisDep, get_redis


__all__ = [
    # auth
    "CurrentUser",
    "get_current_active_user",
    "get_current_user",
    "oauth2_scheme",
    "require_role",
    # db
    "DbSession",
    "get_db",
    # pagination
    "MAX_LIMIT",
    "Pagination",
    "PaginationDep",
    # redis
    "RedisDep",
    "get_redis",
]
