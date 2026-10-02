from app.crud.appointment import (
    create_appointment,
    delete_appointment,
    get_appointment,
    get_appointments,
    get_appointments_by_client,
    get_appointments_by_master,
    update_appointment,
)
from app.crud.master import (
    create_master,
    delete_master,
    get_master,
    get_masters,
    get_masters_by_salon,
    update_master,
)
from app.crud.salon import (
    create_salon,
    delete_salon,
    get_salon,
    get_salons,
    get_salons_by_owner,
    update_salon,
)
from app.crud.service import (
    create_service,
    delete_service,
    get_service,
    get_services,
    get_services_by_salon,
    update_service,
)
from app.crud.user import (
    create_user,
    delete_user,
    get_user,
    get_user_by_email,
    get_users,
    update_user,
)

__all__ = [
    # appointment
    "create_appointment",
    "delete_appointment",
    "get_appointment",
    "get_appointments",
    "get_appointments_by_client",
    "get_appointments_by_master",
    "update_appointment",
    # master
    "create_master",
    "delete_master",
    "get_master",
    "get_masters",
    "get_masters_by_salon",
    "update_master",
    # salon
    "create_salon",
    "delete_salon",
    "get_salon",
    "get_salons",
    "get_salons_by_owner",
    "update_salon",
    # service
    "create_service",
    "delete_service",
    "get_service",
    "get_services",
    "get_services_by_salon",
    "update_service",
    # user
    "create_user",
    "delete_user",
    "get_user",
    "get_user_by_email",
    "get_users",
    "update_user",
]
