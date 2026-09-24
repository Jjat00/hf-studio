from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración leída del entorno o de `.env`. Las credenciales de Higgsfield nunca salen del servidor."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # La consola de Higgsfield entrega la credencial como una sola cadena `KEY_ID:KEY_SECRET`
    # (el SDK oficial la lee así). También se aceptan las dos partes por separado.
    hf_api_key: SecretStr = SecretStr("")
    hf_api_key_id: str = ""
    hf_api_key_secret: SecretStr = SecretStr("")
    hf_base_url: str = "https://api.higgsfield.ai"

    # ElevenLabs (cambio de voz). Opcional: sin clave, las rutas /v1/voice responden 503.
    elevenlabs_api_key: SecretStr = SecretStr("")
    elevenlabs_base_url: str = "https://api.elevenlabs.io"
    elevenlabs_sts_model: str = "eleven_multilingual_sts_v2"
    # Tarifa de pago por uso del Voice Changer por API (a 2026-09-24); con plan se descuenta de sus minutos.
    elevenlabs_usd_per_minute: float = 0.12

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
        return bool(self.hf_credential)

    @property
    def hf_credential(self) -> str:
        """Valor para `Authorization: Key <valor>`: la clave única o `id:secret`."""
        single = self.hf_api_key.get_secret_value().strip()
        if single:
            return single.removeprefix("Key ").strip()
        secret = self.hf_api_key_secret.get_secret_value()
        return f"{self.hf_api_key_id}:{secret}" if self.hf_api_key_id and secret else ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
