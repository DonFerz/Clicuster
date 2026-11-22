"""Работа с часовыми поясами.

ДОБАВЛЕНО 22.11.2026 (аудит/исправления): единая точка приведения даты-времени
к UTC. В приложении все моменты времени хранятся в ``timestamptz`` (UTC),
а API принимает ISO-8601 со смещением. Наивные (без таймзоны) значения
запрещены на уровне Pydantic-схем, чтобы не было «плавающих» записей.
"""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Текущий момент времени в UTC (timezone-aware)."""
    return datetime.now(timezone.utc)


def to_utc(value: datetime) -> datetime:
    """Приводит timezone-aware datetime к UTC.

    Наивное значение — ошибка программиста: API-схемы такие значения не
    пропускают, поэтому здесь бросаем ValueError, а не угадываем зону.
    """
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Naive datetime is not allowed, provide timezone")

    return value.astimezone(timezone.utc)


__all__ = ["to_utc", "utcnow"]
