from pydantic_settings import BaseSettings, SettingsConfigDict


class EnvironmentSettings(BaseSettings):
    DJANGO_SETTINGS_MODULE: str = "config.settings"
    DEBUG: bool = False
    SECRET_KEY: str
    ALLOWED_HOSTS: list[str] = ["localhost", "127.0.0.1"]

    DB_NAME: str = "pets_db"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"
    DB_HOST: str = "localhost"
    DB_PORT: str = "5432"

    REDIS_URL: str = "redis://localhost:6379/0"

    # Automatically reads from the .env file
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


env = EnvironmentSettings()
