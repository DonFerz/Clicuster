"""Публичный API пакета `app.crud`.

ИЗМЕНЕНО 22.11.2026 (аудит/исправления): добавлены новые функции
(подсчёт для пагинации, блокировка мастера, поиск профиля по пользователю,
админское обновление, проверка пересечения записей).
"""

from app.crud.appointment import (
    count_appointments,
    create_appointment,
    delete_appointment,
    get_appointment,
    has_overlapping_appointment,
    list_appointments,
    update_appointment,
)
from app.crud.master import (
    add_service_to_master,
    count_masters,
    create_master,
    delete_master,
    get_master,
    get_master_by_user_id,
    get_master_with_services,
    get_masters,
    get_masters_by_salon,
    lock_master,
    remove_service_from_master,
    update_master,
)
from app.crud.salon import (
    count_salons,
    create_salon,
    delete_salon,
    get_salon,
    get_salons,
    get_salons_by_owner,
    update_salon,
)
from app.crud.service import (
    count_services,
    create_service,
    delete_service,
    get_service,
    get_services,
    get_services_by_salon,
    update_service,
)
from app.crud.user import (
    count_active_admins,
    count_users,
    create_user,
    delete_user,
    get_user,
    get_user_by_email,
    get_users,
    set_user_password,
    update_user,
    update_user_admin,
)

__all__ = [
    # appointment
    "count_appointments",
    "create_appointment",
    "delete_appointment",
    "get_appointment",
    "has_overlapping_appointment",
    "list_appointments",
    "update_appointment",
    # master
    "add_service_to_master",
    "count_masters",
    "create_master",
    "delete_master",
    "get_master",
    "get_master_by_user_id",
    "get_master_with_services",
    "get_masters",
    "get_masters_by_salon",
    "lock_master",
    "remove_service_from_master",
    "update_master",
    # salon
    "count_salons",
    "create_salon",
    "delete_salon",
    "get_salon",
    "get_salons",
    "get_salons_by_owner",
    "update_salon",
    # service
    "count_services",
    "create_service",
    "delete_service",
    "get_service",
    "get_services",
    "get_services_by_salon",
    "update_service",
    # user
    "count_active_admins",
    "count_users",
    "create_user",
    "delete_user",
    "get_user",
    "get_user_by_email",
    "get_users",
    "set_user_password",
    "update_user",
    "update_user_admin",
]
