from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    env: str = "dev"  # dev | prod; dev tokens and insecure cookies work only in dev
    # The app connects as the least-privileged tenet_api role, so row-level security binds it.
    # Migrations and the seed script use the owner role.
    database_url: str = "postgresql+psycopg://tenet_api:tenet_api@localhost:5432/tenet"
    migration_database_url: str = "postgresql+psycopg://tenet:tenet@localhost:5432/tenet"
    test_database_url: str = "postgresql+psycopg://tenet:tenet@localhost:5432/tenet_test"
    test_api_database_url: str = (
        "postgresql+psycopg://tenet_api:tenet_api@localhost:5432/tenet_test"
    )
    public_url: str = "http://localhost:8000"
    web_url: str = "http://localhost:3000"

    # Sessions
    session_idle_hours: int = 12
    session_max_days: int = 7

    # Sign-in (OpenID Connect). Google may reuse the Drive OAuth client; add the sign-in redirect
    # URI {public_url}/api/auth/google/callback to it.
    google_signin_client_id: str | None = None
    google_signin_client_secret: str | None = None
    microsoft_client_id: str | None = None
    microsoft_client_secret: str | None = None

    # Optional separate key for encrypting connector tokens at rest (else derived from secret_key)
    token_encryption_key: str | None = None

    @property
    def dev(self) -> bool:
        return self.env == "dev"

    # LLM gateway: cheap model for routing/classification, strong model for conflict + PR analysis.
    anthropic_api_key: str | None = None
    llm_model_cheap: str = "claude-haiku-5-5"
    llm_model_strong: str = "claude-opus-5-5"

    # GitHub App (milestone 3)
    github_app_id: str | None = None
    github_private_key: str | None = None  # path to the .pem file
    github_webhook_secret: str | None = None
    github_api_url: str = "https://api.github.com"

    # Signs short-lived values such as OAuth state. Set a long random value outside local dev.
    secret_key: str = "dev-only-secret-change-me"

    # Google Drive connector: each person connects their own account (read-only Drive scope).
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str | None = None  # default: {public_url}/api/connect/google/callback
    drive_sync_minutes: int = 15  # 0 turns background sync off

    # Slack app (milestone 7)
    slack_bot_token: str | None = None
    slack_signing_secret: str | None = None
    slack_channel: str = "#payments"


@lru_cache
def get_settings() -> Settings:
    return Settings()
