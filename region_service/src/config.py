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

    app_name: str = "FailoverLab Regional Service"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    # Regional identity
    region_id: str = Field(default="region-a", description="'region-a' or 'region-b'")
    region_name: str = Field(default="Mumbai", description="'Mumbai' or 'Singapore'")
    cloud_zone: str = Field(default="ap-south-1", description="'ap-south-1' or 'ap-southeast-1'")
    initial_role: str = Field(default="ACTIVE", description="'ACTIVE' or 'STANDBY'")
    initial_epoch: int = Field(default=101, description="Monotonically increasing generation epoch")

    # Networking
    host: str = "0.0.0.0"
    port: int = 8001
    cors_origins: List[str] = ["*"]

    # Database
    database_url: str = Field(
        default="sqlite+aiosqlite:///./region_data.db",
        description="Async SQLAlchemy database URL for this region"
    )

    # Security
    internal_api_secret: Optional[str] = None

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        if v.startswith("postgresql://") and not v.startswith("postgresql+asyncpg://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    @property
    def sanitized_database_url(self) -> str:
        if "@" in self.database_url:
            prefix = self.database_url.split("://")[0]
            rest = self.database_url.split("@")[1]
            return f"{prefix}://***:***@{rest}"
        return self.database_url


settings = Settings()

