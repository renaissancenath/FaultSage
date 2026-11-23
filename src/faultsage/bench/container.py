"""Isolated case execution (SR-24, SR-25): Docker Engine or Podman, non-root user, network off
after dependency install, CPU and memory limits, per-case timeout, only the case folder mounted.

FAULTSAGE_BENCH_INSTALL_ARGS adds extra `docker run` arguments to the install step only (the one
step that has network), for example a proxy and CA bundle on a restricted machine. Test steps
always run with --network=none.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

IMAGE_FOR = {"3.6": "python:3.6-slim", "3.7": "python:3.7-slim", "3.8": "python:3.8-slim"}


class InfrastructureError(RuntimeError):
    """The container engine itself is unavailable: abort the run instead of recording the cases
    as excluded, which would wrongly blame the benchmark cases."""


@dataclass(frozen=True, slots=True)
class StepResult:
    returncode: int
    output: str


def engine() -> str | None:
    for name in ("docker", "podman"):
        if shutil.which(name):
            return name
    return None


def image_for(python_version: str) -> str:
    mm = ".".join(python_version.split(".")[:2])
    return IMAGE_FOR.get(mm, "python:3.8-slim")


def run_step(
    case_dir: Path,
    image: str,
    script: str,
    *,
    network: bool,
    timeout: int,
    workdir: str = "/case",
    cpus: str = "1",
    memory: str = "3g",
    extra_mounts: list[tuple[Path, str]] | None = None,
) -> StepResult:
    eng = engine()
    if eng is None:
        return StepResult(
            127, "No container engine found. Install Docker Engine or Podman in WSL2."
        )
    cmd = [
        eng,
        "run",
        "--rm",
        f"--cpus={cpus}",
        f"--memory={memory}",
        "--pids-limit=512",
        "--security-opt=no-new-privileges",
        "-v",
        f"{case_dir.resolve()}:/case",
        "-w",
        workdir,
        "--user",
        "1000:1000",
        "-e",
        "HOME=/case/home",
        "-e",
        "PIP_DISABLE_PIP_VERSION_CHECK=1",
        "-e",
        "PYTHONDONTWRITEBYTECODE=1",
    ]
    for host, target in extra_mounts or []:
        cmd += ["-v", f"{host.resolve()}:{target}"]
    if network:
        cmd += shlex.split(os.environ.get("FAULTSAGE_BENCH_INSTALL_ARGS", ""))
    else:
        cmd.append("--network=none")
    cmd += [image, "bash", "-c", script]
    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return StepResult(124, f"Timed out after {timeout} s.")
    out = (res.stdout + res.stderr)[-60_000:]
    if res.returncode != 0 and (
        "Cannot connect to the Docker daemon" in out or "Is the docker daemon running" in out
    ):
        raise InfrastructureError(
            "The container engine is not reachable. Start Docker and run again."
        )
    return StepResult(res.returncode, out)
