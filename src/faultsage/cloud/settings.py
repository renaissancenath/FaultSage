"""FaultSage Cloud settings, read from environment variables (see .env.example)."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from functools import lru_cache


def _bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    environment: str = "development"  # development | staging | production
    database_url: str = "sqlite:///./faultsage-cloud.db"
    secret_key: str = ""
    base_url: str = "http://localhost:8000"
    allow_signup: bool = True
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_starttls: bool = True
    github_client_id: str = ""
    github_client_secret: str = ""
    billing_provider: str = "none"  # D-017: none until Q-004 is answered
    lemonsqueezy_checkout_url: str = ""
    lemonsqueezy_webhook_secret: str = ""
    support_email: str = ""
    # Shown on the Terms, Privacy and Refunds pages (who is selling, where to complain).
    operator_name: str = ""
    operator_address: str = ""
    grievance_officer: str = ""
    grievance_email: str = ""
    jurisdiction_city: str = ""
    hosting_region: str = ""
    trusted_proxy: bool = (
        False  # true behind Render/Fly/Caddy so client IPs come from X-Forwarded-For
    )
    # How many proxies in front of the app append to X-Forwarded-For (Render: 1, Caddy: 1,
    # Cloudflare in front of Render: 2). The client IP is that many entries from the right.
    proxy_hops: int = 1
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def secure_cookies(self) -> bool:
        return self.base_url.startswith("https://")

    @property
    def github_enabled(self) -> bool:
        return bool(self.github_client_id and self.github_client_secret)

    @property
    def smtp_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)

    @property
    def billing_enabled(self) -> bool:
        return self.billing_provider == "lemonsqueezy" and bool(self.lemonsqueezy_checkout_url)


def environment_from_env() -> str:
    return os.environ.get("FAULTSAGE_ENV", "development")


def database_url_from_env() -> str:
    """DATABASE_URL in SQLAlchemy form. Database commands (backup, restore, migrate) need only this
    and the environment name, not the web app's secrets."""
    url = os.environ.get("DATABASE_URL", "sqlite:///./faultsage-cloud.db")
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    env = environment_from_env()
    secret = os.environ.get("FAULTSAGE_SECRET_KEY", "")
    if not secret:
        if env == "production":
            raise RuntimeError("FAULTSAGE_SECRET_KEY must be set in production (32+ random bytes).")
        secret = secrets.token_urlsafe(32)  # dev only: sessions reset on restart
    url = database_url_from_env()
    return Settings(
        environment=env,
        database_url=url,
        secret_key=secret,
        base_url=os.environ.get("FAULTSAGE_BASE_URL", "http://localhost:8000").rstrip("/"),
        allow_signup=_bool("FAULTSAGE_ALLOW_SIGNUP", True),
        smtp_host=os.environ.get("SMTP_HOST", ""),
        smtp_port=int(os.environ.get("SMTP_PORT", "587")),
        smtp_user=os.environ.get("SMTP_USER", ""),
        smtp_password=os.environ.get("SMTP_PASSWORD", ""),
        smtp_from=os.environ.get("SMTP_FROM", ""),
        smtp_starttls=_bool("SMTP_STARTTLS", True),
        github_client_id=os.environ.get("GITHUB_CLIENT_ID", ""),
        github_client_secret=os.environ.get("GITHUB_CLIENT_SECRET", ""),
        billing_provider=os.environ.get("BILLING_PROVIDER", "none"),
        lemonsqueezy_checkout_url=os.environ.get("LEMONSQUEEZY_CHECKOUT_URL", ""),
        lemonsqueezy_webhook_secret=os.environ.get("LEMONSQUEEZY_WEBHOOK_SECRET", ""),
        support_email=os.environ.get("FAULTSAGE_SUPPORT_EMAIL", ""),
        operator_name=os.environ.get("FAULTSAGE_OPERATOR_NAME", ""),
        operator_address=os.environ.get("FAULTSAGE_OPERATOR_ADDRESS", ""),
        grievance_officer=os.environ.get("FAULTSAGE_GRIEVANCE_OFFICER", ""),
        grievance_email=os.environ.get("FAULTSAGE_GRIEVANCE_EMAIL", ""),
        jurisdiction_city=os.environ.get("FAULTSAGE_JURISDICTION_CITY", ""),
        hosting_region=os.environ.get("FAULTSAGE_HOSTING_REGION", ""),
        trusted_proxy=_bool("FAULTSAGE_TRUSTED_PROXY", False),
        proxy_hops=max(1, int(os.environ.get("FAULTSAGE_PROXY_HOPS", "1") or "1")),
    )
