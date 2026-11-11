from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Service identification
    app_name: str = "FailoverLab Controller Service"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    # Server configuration
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "*"
    ]

    # Database configuration (defaults to async sqlite for local ease, supports asyncpg for Postgres)
    database_url: str = Field(
        default="sqlite+aiosqlite:///./controller.db",
        description="Async SQLAlchemy database URL"
    )

    # Downstream service URLs
    gateway_url: str = "http://localhost:8080"
    region_a_url: str = "http://localhost:8001"
    region_b_url: str = "http://localhost:8002"

    # Execution flags
    simulation_mode: bool = True  # If downstream services offline, synthesize verified responses
    internal_api_secret: str = "internal-secret-token"

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        # Normalize postgres:// to postgresql+asyncpg:// if needed
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        if v.startswith("postgresql://") and not v.startswith("postgresql+asyncpg://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    @property
    def sanitized_database_url(self) -> str:
        """Safe database URL string for logging and metrics without leaking passwords."""
        if "@" in self.database_url:
            prefix = self.database_url.split("://")[0]
            rest = self.database_url.split("@")[1]
            return f"{prefix}://***:***@{rest}"
        return self.database_url


settings = Settings()

