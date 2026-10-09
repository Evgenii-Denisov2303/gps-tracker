from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Login(StrictModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)
    remember_me: bool = False


class VehicleIn(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    plate: str = Field(default="", max_length=30)
    description: str = Field(default="", max_length=500)


class DeviceIn(StrictModel):
    name: str = Field(min_length=1, max_length=100)


class HardwareDeviceIn(DeviceIn):
    imei: str = Field(pattern=r"^[0-9]{15}$")


class PointIn(StrictModel):
    event_id: UUID
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    speed: float | None = Field(default=None, ge=0, le=400)
    accuracy: float = Field(gt=0, le=100000)
    heading: float | None = Field(default=None, ge=0, lt=360)
    battery_level: int | None = Field(default=None, ge=0, le=100)
    charging: bool | None = None
    gps_timestamp: datetime

    @field_validator("gps_timestamp")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None or value.year < 2020:
            raise ValueError("GPS timestamp requires timezone and year >= 2020")
        return value


class BatchIn(StrictModel):
    points: list[PointIn] = Field(min_length=1, max_length=500)


class HeartbeatIn(StrictModel):
    app_version: str = Field(min_length=1, max_length=32, pattern=r"^[0-9A-Za-z.+-]+$")
    battery_level: int | None = Field(default=None, ge=0, le=100)
    charging: bool | None = None
    gps_enabled: bool
    location_permission: bool
    background_permission: bool
    battery_optimization_exempt: bool
    gps_age_seconds: int | None = Field(default=None, ge=0, le=2147483647)
    queue_count: int = Field(ge=0, le=2147483647)
