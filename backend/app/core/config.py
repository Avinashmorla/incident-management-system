from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Incident Management System"
    queue_max_size: int = 10000
    debounce_window_seconds: int = 10
    ingestion_rate_per_minute: int = 60000
    data_dir: Path = Path("data")


settings = Settings()
