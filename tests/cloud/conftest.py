"""Cloud tests run on SQLite by default and on PostgreSQL when FAULTSAGE_TEST_DATABASE_URL is set
(the CI postgres job). Each test gets an empty database."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from faultsage.cloud import security
from faultsage.cloud.settings import get_settings
from faultsage.cloud.storage import db

PASSWORD = "correct horse battery staple"


@pytest.fixture
def cloud(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    pg = os.environ.get("FAULTSAGE_TEST_DATABASE_URL")
    schema = None
    if pg:
        from sqlalchemy import create_engine

        schema = "t_" + uuid.uuid4().hex[:10]
        admin = create_engine(pg)
        with admin.begin() as c:
            c.execute(text(f"CREATE SCHEMA {schema}"))
        url = pg + ("&" if "?" in pg else "?") + f"options=-csearch_path%3D{schema}"
    else:
        url = f"sqlite:///{tmp_path / 'cloud.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("FAULTSAGE_BASE_URL", "http://localhost:8000")
    get_settings.cache_clear()
    db.set_engine(None)
    security.limiter.reset()
    from faultsage.cloud.app import create_app

    with TestClient(create_app(), base_url="http://localhost:8000") as c:
        yield c
    db.engine().dispose()
    db.set_engine(None)
    get_settings.cache_clear()
    if pg and schema:
        with admin.begin() as c:
            c.execute(text(f"DROP SCHEMA {schema} CASCADE"))  # test-only scratch schema


def signup(c: TestClient, email: str = "ana@example.com", **extra: str) -> dict[str, str]:
    r = c.post("/api/v1/auth/signup", json={"email": email, "password": PASSWORD, **extra})
    assert r.status_code == 201, r.text
    return {"X-CSRF-Token": c.cookies.get("fs_csrf") or ""}


def project_with_key(c: TestClient, h: dict[str, str], name: str = "shop") -> tuple[int, str]:
    pid = c.post(
        "/api/v1/projects",
        json={"name": name, "repo_url": "https://github.com/acme/shop"},
        headers=h,
    ).json()["id"]
    key = c.post(f"/api/v1/projects/{pid}/keys", json={"name": "k"}, headers=h).json()["key"]
    return pid, key
