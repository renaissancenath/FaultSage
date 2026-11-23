"""Seed a fresh cloud server through its real API, the SDK and the CLI (screenshots and demos).

Usage: python tools/seed_cloud.py BASE_URL WORKDIR
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import httpx


def main() -> int:
    base, work = sys.argv[1], Path(sys.argv[2])
    c = httpx.Client(base_url=base, timeout=20)
    c.post(
        "/api/v1/auth/signup",
        json={
            "email": "ana@example.com",
            "password": "correct horse battery staple",
            "name": "Ana",
            "workspace": "Acme",
        },
    ).raise_for_status()
    h = {"X-CSRF-Token": c.cookies.get("fs_csrf") or ""}
    pid = c.post(
        "/api/v1/projects",
        json={"name": "checkout-api", "repo_url": "https://github.com/acme/checkout-api"},
        headers=h,
    ).json()["id"]
    pid2 = c.post("/api/v1/projects", json={"name": "churn"}, headers=h).json()["id"]
    k1 = c.post(f"/api/v1/projects/{pid}/keys", json={"name": "production"}, headers=h).json()[
        "key"
    ]
    k2 = c.post(f"/api/v1/projects/{pid2}/keys", json={"name": "laptop"}, headers=h).json()["key"]
    app = work / "shopapp" / "shop"
    app.mkdir(parents=True, exist_ok=True)
    (app / "__init__.py").write_text("")
    (app / "cart.py").write_text(
        "class Cart:\n    def __init__(self, items):\n        self.items = items\n\n"
        "    def total(self, discount):\n        return sum(self.items) * (1 - discount.rate)\n"
    )
    (app / "views.py").write_text(
        "from shop.cart import Cart\n\n\ndef checkout(user):\n    cart = Cart([10, 20])\n"
        '    return cart.total(user.get("discount"))\n'
    )
    code = (
        "import faultsage.sdk as fs\nfs.init(environment='production')\nfrom shop.views import checkout\n"
        "try:\n    checkout({'name': 'x'})\nexcept Exception as e:\n    fs.capture_exception(e, route='/checkout')\n"
        "fs.flush()\n"
    )
    for release in ("1.4.1", "1.4.2", "1.4.2"):
        env = {
            **os.environ,
            "FAULTSAGE_URL": base,
            "FAULTSAGE_API_KEY": k1,
            "FAULTSAGE_RELEASE": release,
        }
        subprocess.run([sys.executable, "-c", code], cwd=work / "shopapp", env=env, check=True)
    env = {**os.environ, "FAULTSAGE_HOME": str(work / "fshome")}
    churn = work / "churn"
    subprocess.run(
        ["faultsage", "cloud", "login", "--url", base, "--api-key", k2],
        cwd=churn,
        env=env,
        check=True,
    )
    subprocess.run(["faultsage", "cloud", "push", "all"], cwd=churn, env=env, check=True)
    print(json.dumps({"projects": [pid, pid2]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
