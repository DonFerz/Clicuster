# syntax=docker/dockerfile:1
# ============================================================
#  Clicuster — Dockerfile
#
#  ИЗМЕНЕНО 22.11.2026 (аудит/исправления):
#   • в runtime-образ больше НЕ ставятся dev-зависимости
#     (requirements-dev.txt: pytest, black, mypy, ipython и т.п.) — это
#     уменьшало образ и расширяло поверхность атаки;
#   • контейнер работает от непривилегированного пользователя appuser,
#     а не от root;
#   • добавлен scripts/docker-entrypoint.sh: перед стартом API применяет
#     миграции Alembic (иначе «чистый» docker compose up падал на пустой БД);
#   • копируются только нужные каталоги (app, alembic, scripts), а не весь
#     контекст сборки.
# ============================================================

# ---------- Builder ----------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt


# ---------- Runtime ----------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system appuser \
    && useradd --system --gid appuser --create-home appuser

COPY --from=builder /opt/venv /opt/venv

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts

# Убираем тесты из рантайм-образа и делаем entrypoint исполняемым.
RUN rm -rf /app/app/tests /app/app/**/__pycache__ \
    && chmod +x /app/scripts/docker-entrypoint.sh \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
