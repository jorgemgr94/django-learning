import json

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EnvironmentSettings(BaseSettings):
    DJANGO_SETTINGS_MODULE: str = "config.settings.local"
    DEBUG: bool = False
    SECRET_KEY: str
    ALLOWED_HOSTS: list[str] = ["localhost", "127.0.0.1"]

    DB_NAME: str = "pets_db"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"
    DB_HOST: str = "localhost"
    DB_PORT: str = "5432"

    REDIS_URL: str = "redis://localhost:6380/0"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    @field_validator("ALLOWED_HOSTS", mode="before")
    @classmethod
    def split_allowed_hosts(cls, v: object) -> list[str]:
        """Accept JSON list in env or comma-separated hosts."""
        if isinstance(v, str):
            stripped = v.strip()
            if stripped.startswith("["):
                parsed = json.loads(stripped)
                if not isinstance(parsed, list):
                    raise ValueError("ALLOWED_HOSTS JSON must be a list")
                return [str(x).strip() for x in parsed if str(x).strip()]
            return [h.strip() for h in v.split(",") if h.strip()]
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        raise TypeError("ALLOWED_HOSTS must be a str or list[str]")


env = EnvironmentSettings()
