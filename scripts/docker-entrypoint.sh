#!/bin/sh
# ============================================================
#  Точка входа контейнера.
#
#  ДОБАВЛЕНО 22.11.2026 (аудит/исправления): раньше миграции нужно было
#  применять вручную (`docker compose exec app alembic upgrade head`),
#  и «с нуля» API падал на отсутствующих таблицах.
#
#  Поведение:
#    * ждём доступность PostgreSQL (до 30 секунд);
#    * применяем миграции Alembic;
#    * запускаем переданную команду (uvicorn / воркер).
#  Флаг RUN_MIGRATIONS=0 отключает авто-миграции (например, для воркера,
#  чтобы миграции не запускались дважды).
# ============================================================
set -e

RUN_MIGRATIONS="${RUN_MIGRATIONS:-1}"

if [ "$RUN_MIGRATIONS" = "1" ]; then
    echo "[entrypoint] applying database migrations..."
    attempt=1
    while [ "$attempt" -le 30 ]; do
        if alembic upgrade head; then
            break
        fi
        echo "[entrypoint] database is not ready (attempt $attempt/30)"
        attempt=$((attempt + 1))
        sleep 1
    done

    if [ "$attempt" -gt 30 ]; then
        echo "[entrypoint] could not apply migrations" >&2
        exit 1
    fi
fi

echo "[entrypoint] starting: $*"
exec "$@"
