"""Зависимость FastAPI для пагинации списков.

Использование в роутере:

    @router.get("/users")
    async def list_users(
        pagination: PaginationDep,
        db: DbSession,
    ):
        users = await get_users(db, skip=pagination.skip, limit=pagination.limit)
        return users

"""

from typing import Annotated

from fastapi import Depends
from pydantic import BaseModel, Field


MAX_LIMIT = 100


class Pagination(BaseModel):
    skip: int = Field(
        default=0,
        ge=0,
        description="Сколько записей пропустить",
    )
    limit: int = Field(
        default=20,
        ge=1,
        le=MAX_LIMIT,
        description=f"Сколько записей вернуть (1..{MAX_LIMIT})",
    )


PaginationDep = Annotated[Pagination, Depends()]


__all__ = ["MAX_LIMIT", "Pagination", "PaginationDep"]
