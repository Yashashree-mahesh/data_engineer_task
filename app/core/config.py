from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Corporate Credit Rating Data Platform"
    database_url: str = "postgresql+psycopg://ratings:ratings@postgres:5432/ratings"
    data_dir: Path = Path("/app/data")
    reports_dir: Path = Path("/app/reports")
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="")


@lru_cache
def get_settings() -> Settings:
    return Settings()
