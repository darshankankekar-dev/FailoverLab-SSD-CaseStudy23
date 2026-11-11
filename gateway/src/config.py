from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8080
    
    default_target: str = "region-a"
    
    # Regional target URL configuration
    region_a_url: str = "http://localhost:8001"
    region_b_url: str = "http://localhost:8002"
    controller_url: str = "http://localhost:8000"
    
    dns_ttl_seconds: int = 2
    propagation_percent: int = 100
    
    internal_token: str = "internal-secret-token"
    simulation_mode: bool = False
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
