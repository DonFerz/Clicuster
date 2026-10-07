from __future__ import annotations

import logging
from typing import Any, ClassVar

__all__ = [
    "AppError",
    "AuthenticationError",
    "PermissionDeniedError",
    "NotFoundError",
    "ConflictError",
    "ValidationError",
    "RateLimitError",
    "ExternalServiceError",
    "ServiceUnavailableError",
]


# ---------------------------------------------------------------------------
# Базовое исключение
# ---------------------------------------------------------------------------


class AppError(Exception):
    """Базовое исключение приложения.

    Контракт конструктора (единый для всех подклассов):
        * первый позиционный аргумент — всегда ``detail``;
        * дополнительные структурированные поля — keyword-only;
        * подклассы добавляют поля в ответ через ``_additional_payload()``.

    Атрибуты класса:
        status_code: HTTP-код ответа по умолчанию.
        code: машиночитаемый код ошибки для клиента.
        default_detail: текст по умолчанию, если ``detail`` не передан.
        log_level: уровень логирования (см. ``logging``).
        log_traceback: писать ли стектрейс в лог.
    """

    status_code: ClassVar[int] = 500
    code: ClassVar[str] = "internal_error"
    default_detail: ClassVar[str] = "Internal server error"
    log_level: ClassVar[int] = logging.ERROR
    log_traceback: ClassVar[bool] = True

    def __init__(
        self,
        detail: str | None = None,
        *,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.detail: str = detail or self.default_detail
        # Копируем словарь, чтобы не расшарить его между исключениями/логами.
        self.extra: dict[str, Any] = dict(extra) if extra else {}
        super().__init__(self.detail)

    def _additional_payload(self) -> dict[str, Any]:
        """Доп. поля для ``to_dict``. Переопределяется в подклассах."""
        return {}

    def to_dict(self) -> dict[str, Any]:
        """Сериализуемое представление для тела HTTP-ответа."""
        payload: dict[str, Any] = {"code": self.code, "detail": self.detail}
        if self.extra:
            payload["extra"] = self.extra
        payload.update(self._additional_payload())
        return payload

    def __repr__(self) -> str:  # pragma: no cover
        return f"{type(self).__name__}(code={self.code!r}, detail={self.detail!r})"


# ---------------------------------------------------------------------------
# 401
# ---------------------------------------------------------------------------


class AuthenticationError(AppError):
    """Пользователь не аутентифицирован."""

    status_code: ClassVar[int] = 401
    code: ClassVar[str] = "not_authenticated"
    default_detail: ClassVar[str] = "Not authenticated"
    log_level: ClassVar[int] = logging.WARNING
    log_traceback: ClassVar[bool] = False


# ---------------------------------------------------------------------------
# 403
# ---------------------------------------------------------------------------


class PermissionDeniedError(AppError):
    """Пользователь аутентифицирован, но не имеет прав доступа."""

    status_code: ClassVar[int] = 403
    code: ClassVar[str] = "permission_denied"
    default_detail: ClassVar[str] = "Permission denied"
    log_level: ClassVar[int] = logging.WARNING
    log_traceback: ClassVar[bool] = False


# ---------------------------------------------------------------------------
# 404
# ---------------------------------------------------------------------------


class NotFoundError(AppError):
    """Запрошенная сущность не найдена.

        NotFoundError(detail="custom text")           # → "custom text"
        NotFoundError(entity="User", entity_id=42)    # → "User (id=42) not found"
        NotFoundError(entity="Salon")                 # → "Salon not found"
        NotFoundError.by_id("User", 42)               # удобная фабрика
    """

    status_code: ClassVar[int] = 404
    code: ClassVar[str] = "not_found"
    default_detail: ClassVar[str] = "Not found"
    log_level: ClassVar[int] = logging.WARNING
    log_traceback: ClassVar[bool] = False

    def __init__(
        self,
        detail: str | None = None,
        *,
        entity: str | None = None,
        entity_id: int | str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.entity = entity
        self.entity_id = entity_id

        if detail is None:
            if entity is None:
                detail = self.default_detail
            else:
                suffix = f" (id={entity_id})" if entity_id is not None else ""
                detail = f"{entity}{suffix} not found"

        super().__init__(detail, extra=extra)

    def _additional_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.entity is not None:
            payload["entity"] = self.entity
        if self.entity_id is not None:
            payload["entity_id"] = self.entity_id
        return payload

    @classmethod
    def by_id(cls, entity: str, entity_id: int | str) -> "NotFoundError":
        """Удобная фабрика: ``NotFoundError.by_id("User", 42)``."""
        return cls(entity=entity, entity_id=entity_id)


# ---------------------------------------------------------------------------
# 409
# ---------------------------------------------------------------------------


class ConflictError(AppError):
    """Конфликт состояния: дубликат, гонка, нарушение уникальности.

        ConflictError("Email already registered")
        ConflictError(entity="User", entity_id=42)
        ConflictError.already_exists("User", 42)
    """

    status_code: ClassVar[int] = 409
    code: ClassVar[str] = "conflict"
    default_detail: ClassVar[str] = "Resource conflict"
    log_level: ClassVar[int] = logging.WARNING
    log_traceback: ClassVar[bool] = False

    def __init__(
        self,
        detail: str | None = None,
        *,
        entity: str | None = None,
        entity_id: int | str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.entity = entity
        self.entity_id = entity_id

        if detail is None and entity is not None:
            suffix = f" (id={entity_id})" if entity_id is not None else ""
            detail = f"{entity}{suffix} already exists"

        super().__init__(detail, extra=extra)

    def _additional_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.entity is not None:
            payload["entity"] = self.entity
        if self.entity_id is not None:
            payload["entity_id"] = self.entity_id
        return payload

    @classmethod
    def already_exists(
        cls, entity: str, entity_id: int | str | None = None
    ) -> "ConflictError":
        return cls(entity=entity, entity_id=entity_id)


# ---------------------------------------------------------------------------
# 422
# ---------------------------------------------------------------------------


class ValidationError(AppError):
    """Ошибка валидации, неверные данные.

        ValidationError(fields={"email": "invalid format"})
    """

    status_code: ClassVar[int] = 422
    code: ClassVar[str] = "validation_error"
    default_detail: ClassVar[str] = "Validation error"
    log_level: ClassVar[int] = logging.INFO
    log_traceback: ClassVar[bool] = False

    def __init__(
        self,
        detail: str | None = None,
        *,
        fields: dict[str, str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        # fields: {"email": "invalid format", "age": "must be >= 0"}
        self.fields: dict[str, str] = dict(fields) if fields else {}
        super().__init__(detail, extra=extra)

    def _additional_payload(self) -> dict[str, Any]:
        return {"fields": self.fields} if self.fields else {}


# ---------------------------------------------------------------------------
# 429
# ---------------------------------------------------------------------------


class RateLimitError(AppError):
    """Превышен лимит запросов.

        RateLimitError(retry_after=30)
    """

    status_code: ClassVar[int] = 429
    code: ClassVar[str] = "rate_limit_exceeded"
    default_detail: ClassVar[str] = "Too many requests"
    log_level: ClassVar[int] = logging.WARNING
    log_traceback: ClassVar[bool] = False

    def __init__(
        self,
        detail: str | None = None,
        *,
        retry_after: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.retry_after = retry_after

        if detail is None and retry_after is not None:
            detail = f"Too many requests, retry after {retry_after}s"

        super().__init__(detail, extra=extra)

    def _additional_payload(self) -> dict[str, Any]:
        return (
            {"retry_after": self.retry_after}
            if self.retry_after is not None
            else {}
        )


# ---------------------------------------------------------------------------
# 502
# ---------------------------------------------------------------------------


class ExternalServiceError(AppError):
    """Внешний сервис ответил ошибкой или недоступен.

        ExternalServiceError(service="payments", upstream_status=500)
    """

    status_code: ClassVar[int] = 502
    code: ClassVar[str] = "external_service_error"
    default_detail: ClassVar[str] = "Bad gateway"
    log_level: ClassVar[int] = logging.ERROR
    log_traceback: ClassVar[bool] = True

    def __init__(
        self,
        detail: str | None = None,
        *,
        service: str | None = None,
        upstream_status: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.service = service
        self.upstream_status = upstream_status

        if detail is None and service is not None:
            suffix = (
                f" (upstream status={upstream_status})"
                if upstream_status is not None
                else ""
            )
            detail = f"External service '{service}' is unavailable{suffix}"

        super().__init__(detail, extra=extra)

    def _additional_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.service is not None:
            payload["service"] = self.service
        if self.upstream_status is not None:
            payload["upstream_status"] = self.upstream_status
        return payload


# ---------------------------------------------------------------------------
# 503
# ---------------------------------------------------------------------------


class ServiceUnavailableError(AppError):
    """Сервис временно недоступен (деградация, maintenance, перегрузка).

        ServiceUnavailableError(retry_after=60)
    """

    status_code: ClassVar[int] = 503
    code: ClassVar[str] = "service_unavailable"
    default_detail: ClassVar[str] = "Service temporarily unavailable"
    log_level: ClassVar[int] = logging.ERROR
    log_traceback: ClassVar[bool] = True

    def __init__(
        self,
        detail: str | None = None,
        *,
        retry_after: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.retry_after = retry_after
        super().__init__(detail, extra=extra)

    def _additional_payload(self) -> dict[str, Any]:
        return (
            {"retry_after": self.retry_after}
            if self.retry_after is not None
            else {}
        )
