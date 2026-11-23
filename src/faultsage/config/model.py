"""Config models for .faultsage/config.toml (TRD section 5.4)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

DEFAULT_PORT = 8765
LOOPBACK = "127.0.0.1"


class _Cfg(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectCfg(_Cfg):
    name: str
    root: str = "."


class SignalsCfg(_Cfg):
    pytest: bool = True
    run_wrapper: bool = True
    git: bool = True
    file_watch: bool = True
    logs: list[str] = Field(default_factory=list)
    log_patterns: list[str] = Field(
        default_factory=lambda: ["ERROR", r"Traceback \(most recent call last\)"]
    )


class AnalysisCfg(_Cfg):
    coverage_contexts: bool = False
    blast_radius_depth: int = Field(default=4, ge=1, le=12)


class VerifyCfg(_Cfg):
    timeout_seconds: int = Field(default=600, ge=5, le=7200)
    extra_commands: list[list[str]] = Field(default_factory=list)


class DashboardCfg(_Cfg):
    port: int = Field(default=DEFAULT_PORT, ge=1024, le=65535)
    host: str = LOOPBACK

    @field_validator("host")
    @classmethod
    def _loopback_only(cls, v: str) -> str:
        # SR-1: any other bind address is rejected at config load.
        if v != LOOPBACK:
            raise ValueError("dashboard.host must be 127.0.0.1 (SR-1)")
        return v


class ModelCfg(_Cfg):
    enabled: bool = False
    endpoint: str = "http://127.0.0.1:11434"
    name: str = ""

    @field_validator("endpoint")
    @classmethod
    def _local_only(cls, v: str) -> str:
        if not (v.startswith(("http://127.0.0.1", "http://localhost"))):
            raise ValueError("model.endpoint must be on localhost (SR-6)")
        return v


class RetentionCfg(_Cfg):
    event_days: int = Field(default=30, ge=1, le=3650)


class CloudCfg(_Cfg):
    """Optional FaultSage Cloud sync (D-014). Off by default; no network unless enabled."""

    enabled: bool = False
    url: str = ""
    project_slug: str = ""


class Config(_Cfg):
    project: ProjectCfg
    signals: SignalsCfg = Field(default_factory=SignalsCfg)
    analysis: AnalysisCfg = Field(default_factory=AnalysisCfg)
    verify: VerifyCfg = Field(default_factory=VerifyCfg)
    dashboard: DashboardCfg = Field(default_factory=DashboardCfg)
    model: ModelCfg = Field(default_factory=ModelCfg)
    retention: RetentionCfg = Field(default_factory=RetentionCfg)
    cloud: CloudCfg = Field(default_factory=CloudCfg)
