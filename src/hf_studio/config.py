from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración leída del entorno o de `.env`. Las credenciales de Higgsfield nunca salen del servidor."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    hf_api_key_id: str = ""
    hf_api_key_secret: SecretStr = SecretStr("")
    hf_base_url: str = "https://api.higgsfield.ai"

    database_url: str = "sqlite+aiosqlite:///./data/hf_studio.db"
    storage_dir: Path = Path("./data/files")

    # URL HTTPS pública de este servidor. Si está, cada envío pide webhook a Higgsfield;
    # el sondeo sigue activo como respaldo.
    public_base_url: str | None = None

    # Concurrencia de la cuenta de Higgsfield (ver console.higgsfield.ai). Los trabajos que
    # excedan el límite esperan en cola local en vez de rebotar con 400.
    hf_max_concurrency: int = 4
    max_active_jobs_per_client: int = 10
    job_timeout_seconds: int = 1800
    dedupe_window_seconds: int = 600
    download_outputs: bool = True
    max_upload_bytes: int = 200 * 1024 * 1024

    cors_origins: str = ""
    worker_enabled: bool = True

    @property
    def hf_configured(self) -> bool:
        return bool(self.hf_api_key_id and self.hf_api_key_secret.get_secret_value())

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
