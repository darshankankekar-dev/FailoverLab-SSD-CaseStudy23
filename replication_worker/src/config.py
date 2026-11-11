from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "FailoverLab Replication Worker"
    app_version: str = "0.1.0"
    log_level: str = "INFO"

    # Service endpoints
    controller_url: str = "http://localhost:8000"
    region_a_url: str = "http://localhost:8001"
    region_b_url: str = "http://localhost:8002"

    # Replication parameters
    poll_interval_sec: float = 0.5
    batch_size: int = 50
    nominal_transit_delay_sec: float = 0.8
    injected_delay_sec: float = 0.0
    is_paused: bool = False

    # Worker HTTP Control Server Port
    port: int = 8003
    internal_api_secret: str = ""


settings = Settings()

