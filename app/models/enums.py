import enum


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    CLIENT = "client"
    MASTER = "master"


class SalonType(str, enum.Enum):
    BARBERSHOP = "barbershop"
    BEAUTY_SALON = "beauty_salon"
    HAIRDRESSER = "hairdresser"


class MasterPosition(str, enum.Enum):
    MASTER = "master"
    TOP_MASTER = "top_master"


class RecordStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
