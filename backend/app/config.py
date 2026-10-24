import hashlib
import json
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = ""
    database_schema: str = Field(
        default="geomine", pattern=r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$"
    )
    frontend_origin: str = "http://localhost:5173"
    app_env: str = "development"
    openrouter_api_key: str = ""
    openrouter_model: str = "nvidia/nemotron-3.5-lightning:free"
    pc_subscription_key: str = ""
    model_path: str = ""
    model_manifest_path: str = ""
    session_hours: int = 12
    enable_registration: bool = True
    max_aoi_km2: float = 100
    job_timeout_seconds: int = Field(default=1800, ge=30, le=7200)
    worker_poll_seconds: int = Field(default=4, ge=1, le=60)
    worker_heartbeat_seconds: int = Field(default=10, ge=2, le=30)
    worker_stale_seconds: int = Field(default=60, ge=40, le=300)
    operations_token: str = ""
    backup_encryption_key: str = ""
    firebase_project_id: str = ""
    firebase_web_api_key: str = ""
    firebase_app_id: str = ""
    firebase_service_account_json: str = ""

    @property
    def firebase_enabled(self):
        return bool(
            self.firebase_project_id
            and self.firebase_web_api_key
            and self.firebase_app_id
            and self.firebase_service_account_json
        )

    @property
    def model_available(self):
        if not self.model_path or not self.model_manifest_path:
            return False
        try:
            weights, manifest = Path(self.model_path), Path(self.model_manifest_path)
            return validate_model_files(
                str(weights),
                weights.stat().st_mtime_ns,
                weights.stat().st_size,
                str(manifest),
                manifest.stat().st_mtime_ns,
            )
        except (OSError, ValueError, TypeError):
            return False


@lru_cache
def settings():
    return Settings()


@lru_cache(maxsize=4)
def validate_model_files(
    weights_path, weights_modified, weights_size, manifest_path, manifest_modified
):
    try:
        manifest = json.loads(Path(manifest_path).read_text())
        with Path(weights_path).open("rb") as stream:
            checksum = hashlib.file_digest(stream, "sha256").hexdigest()
        return (
            manifest.get("architecture") == "geomine-xnet-swin-tiny-v1"
            and bool(manifest.get("validation_metrics"))
            and bool(manifest.get("test_metrics"))
            and manifest.get("release_approved") is True
            and manifest.get("sha256") == checksum
        )
    except (OSError, ValueError, TypeError):
        return False
