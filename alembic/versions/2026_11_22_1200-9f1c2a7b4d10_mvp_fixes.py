"""MVP fixes: services.is_active, индексы, защита от двойной записи

Revision ID: 9f1c2a7b4d10
Revises: d23902251914
Create Date: 2026-11-22 12:00:00

ДОБАВЛЕНО 22.11.2026 по итогам аудита:
  1. services.is_active — колонка, которую ожидали схемы ServiceRead и
     ServiceUpdate, но которой не было в БД (список услуг падал с 500).
  2. Приведение email к нижнему регистру (уникальность без учёта регистра).
  3. Индексы по внешним ключам, которые фильтруются в API
     (salons.owner_id, masters.salon_id, services.salon_id).
  4. Составные индексы по записям (master_id/start_time, client_id/start_time).
  5. CHECK end_time > start_time.
  6. EXCLUDE-ограничение «один мастер — один интервал» через btree_gist:
     гарантирует отсутствие двойной записи на уровне БД, даже если два
     процесса одновременно пройдут проверку в приложении.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9f1c2a7b4d10"
down_revision: Union[str, Sequence[str], None] = "d23902251914"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. services.is_active ──
    op.add_column(
        "services",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )

    # ── 2. email в нижнем регистре (регистронезависимая уникальность) ──
    op.execute("UPDATE users SET email = lower(email)")

    # ── 3. Индексы по внешним ключам ──
    op.create_index("ix_salons_owner_id", "salons", ["owner_id"])
    op.create_index("ix_masters_salon_id", "masters", ["salon_id"])
    op.create_index("ix_services_salon_id", "services", ["salon_id"])

    # ── 4. Индексы по записям ──
    op.create_index(
        "ix_appointments_master_start",
        "appointments",
        ["master_id", "start_time"],
    )
    op.create_index(
        "ix_appointments_client_start",
        "appointments",
        ["client_id", "start_time"],
    )

    # ── 5. end_time > start_time ──
    # На всякий случай чиним битые строки (в норме их быть не должно).
    op.execute(
        "UPDATE appointments SET end_time = start_time + interval '1 minute' "
        "WHERE end_time <= start_time"
    )
    op.create_check_constraint(
        "ck_appointments_time_order",
        "appointments",
        "end_time > start_time",
    )

    # ── 6. Защита от двойной записи на уровне БД ──
    # btree_gist нужен, чтобы объединить равенство (master_id) с
    # пересечением диапазонов (tstzrange) в одном EXCLUDE-ограничении.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute(
        """
        ALTER TABLE appointments
        ADD CONSTRAINT ex_appointments_master_no_overlap
        EXCLUDE USING gist (
            master_id WITH =,
            tstzrange(start_time, end_time, '[)') WITH &&
        )
        WHERE (status <> 'cancelled'::recordstatus)
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE appointments DROP CONSTRAINT IF EXISTS "
        "ex_appointments_master_no_overlap"
    )
    # Расширение оставляем: оно может использоваться другими объектами.
    op.drop_constraint(
        "ck_appointments_time_order", "appointments", type_="check"
    )
    op.drop_index("ix_appointments_client_start", table_name="appointments")
    op.drop_index("ix_appointments_master_start", table_name="appointments")
    op.drop_index("ix_services_salon_id", table_name="services")
    op.drop_index("ix_masters_salon_id", table_name="masters")
    op.drop_index("ix_salons_owner_id", table_name="salons")
    op.drop_column("services", "is_active")
