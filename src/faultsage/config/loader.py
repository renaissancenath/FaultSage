"""Read and write .faultsage/config.toml."""

from __future__ import annotations

import hashlib
import shutil
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import tomli_w
from pydantic import ValidationError

from faultsage.config.model import Config
from faultsage.errors import ConfigError, ProjectNotFoundError
from faultsage.paths import find_project_root, secure_mkdir

DATA_DIR = ".faultsage"
CONFIG_NAME = "config.toml"
PIPELINE_NAME = "pipeline.toml"


@dataclass(frozen=True, slots=True)
class ProjectPaths:
    root: Path

    @property
    def data(self) -> Path:
        return self.root / DATA_DIR

    @property
    def config(self) -> Path:
        return self.data / CONFIG_NAME

    @property
    def pipeline(self) -> Path:
        return self.data / PIPELINE_NAME

    @property
    def spool(self) -> Path:
        return self.data / "spool"

    @property
    def rejected(self) -> Path:
        return self.spool / "rejected"

    @property
    def db(self) -> Path:
        return self.data / "faultsage.db"

    @property
    def logs(self) -> Path:
        return self.data / "logs"

    @property
    def backups(self) -> Path:
        return self.data / "backups"

    @property
    def session(self) -> Path:
        return self.data / "session"

    @property
    def lock(self) -> Path:
        return self.data / "daemon.lock"

    @property
    def control(self) -> Path:
        return self.data / "control"

    @property
    def hooks_dir(self) -> Path:
        return self.data / "empty-hooks"

    def ensure(self) -> None:
        for d in (self.data, self.spool, self.rejected, self.logs, self.backups, self.hooks_dir):
            secure_mkdir(d)


def locate(start: Path | None = None) -> ProjectPaths:
    """Find the nearest project with a .faultsage/config.toml, else the nearest project root."""
    here = (start or Path.cwd()).resolve()
    for folder in [here, *here.parents]:
        if (folder / DATA_DIR / CONFIG_NAME).exists():
            return ProjectPaths(folder)
    root = find_project_root(here)
    if root is None:
        raise ProjectNotFoundError(
            "No pyproject.toml, setup.py, requirements file or .git found here or above.",
            "Run faultsage init PATH with the path to your project.",
        )
    return ProjectPaths(root)


def load(paths: ProjectPaths) -> Config:
    if not paths.config.exists():
        raise ConfigError(
            f"No FaultSage config at {paths.config}.", "Run faultsage init in the project folder."
        )
    try:
        data = tomllib.loads(paths.config.read_text(encoding="utf-8"))
        return Config.model_validate(data)
    except (tomllib.TOMLDecodeError, ValidationError) as exc:
        raise ConfigError(f"Config is invalid: {exc}", f"Fix {paths.config} and retry.") from exc


def config_hash(paths: ProjectPaths) -> str:
    return hashlib.sha256(paths.config.read_bytes()).hexdigest() if paths.config.exists() else ""


def save(paths: ProjectPaths, cfg: Config, *, force: bool = False) -> Path | None:
    """Write config. Never overwrites without ``force``; with force, a backup is written first."""
    paths.ensure()
    backup: Path | None = None
    if paths.config.exists():
        if not force:
            raise ConfigError(
                f"{paths.config} already exists.", "Pass --force to replace it (a backup is kept)."
            )
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        backup = paths.config.with_name(f"config.toml.bak-{stamp}")
        shutil.copy2(paths.config, backup)
    data = cfg.model_dump(mode="json")
    paths.config.write_text(tomli_w.dumps(data), encoding="utf-8")
    return backup


def load_pipeline(paths: ProjectPaths) -> list[dict[str, object]]:
    if not paths.pipeline.exists():
        return []
    data = tomllib.loads(paths.pipeline.read_text(encoding="utf-8"))
    steps = data.get("step", [])
    return [s for s in steps if isinstance(s, dict) and "name" in s]
