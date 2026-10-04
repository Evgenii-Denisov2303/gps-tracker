from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./tracker.db"
    public_origin: str = "http://localhost:8000"
    cookie_secure: bool = True
    timezone: str = "Europe/Moscow"
    session_hours: int = 12
    stale_seconds: int = 180
    offline_seconds: int = 600
    max_accuracy_m: float = 80
    max_speed_kmh: float = 180
    stop_radius_m: float = 50
    stop_seconds: int = 300
    max_gap_seconds: int = 180
    web_dir: str = "../web"

    @model_validator(mode="after")
    def check(self):
        ZoneInfo(self.timezone)
        if not 30 <= self.stale_seconds < self.offline_seconds:
            raise ValueError("Require 30 <= STALE_SECONDS < OFFLINE_SECONDS")
        if min(self.session_hours, self.max_gap_seconds, self.stop_seconds,
               self.stop_radius_m, self.max_accuracy_m, self.max_speed_kmh) <= 0:
            raise ValueError("Thresholds must be positive")
        if self.cookie_secure and not self.public_origin.startswith("https://"):
            raise ValueError("Use HTTPS PUBLIC_ORIGIN or COOKIE_SECURE=false for localhost")
        return self


@lru_cache
def settings():
    return Settings()
