from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8080
    
    default_target: str = "region-a"
    
    # Regional target URL configuration
    region_a_url: str = "http://localhost:8001"
    region_b_url: str = "http://localhost:8002"
    region_c_url: str = "http://localhost:8004"
    region_d_url: str = "http://localhost:8005"
    region_e_url: str = "http://localhost:8006"
    controller_url: str = "http://localhost:8000"
    
    dns_ttl_seconds: int = 2
    propagation_percent: int = 100
    
    internal_token: str = "internal-secret-token"
    internal_api_secret: Optional[str] = None
    simulation_mode: bool = False
    log_level: str = "INFO"

    @property
    def effective_internal_token(self) -> str:
        return self.internal_api_secret or self.internal_token
    
    # Telemetry export configuration
    gateway_instance_id: str = "gateway-1"
    telemetry_export_enabled: bool = True
    telemetry_export_interval_seconds: float = 1.0
    telemetry_queue_capacity: int = 100
    telemetry_max_retries: int = 5

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
