"""Billing webhook (D-025): signature first, subscription objects only, newest event wins."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from faultsage.cloud.settings import get_settings
from tests.cloud.conftest import signup

SECRET = "whsec-test-only"
URL = "/api/v1/billing/webhook/lemonsqueezy"


def _org_id(c: TestClient) -> int:
    return int(c.get("/api/v1/me").json()["org"]["id"])


def _plan(c: TestClient) -> str:
    return str(c.get("/api/v1/me").json()["org"]["plan"]["id"])


def _send(
    c: TestClient,
    org: int | str,
    event: str,
    status: str,
    when: str,
    obj_type: str = "subscriptions",
) -> Any:
    body = json.dumps(
        {
            "meta": {"event_name": event, "custom_data": {"org_id": str(org)}},
            "data": {
                "type": obj_type,
                "id": "sub_1",
                "attributes": {"status": status, "updated_at": when},
            },
        }
    ).encode()
    sig = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return c.post(
        URL, content=body, headers={"X-Signature": sig, "Content-Type": "application/json"}
    )


@pytest.fixture
def billed(cloud: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("LEMONSQUEEZY_WEBHOOK_SECRET", SECRET)
    get_settings.cache_clear()
    signup(cloud, "owner@example.com")
    return cloud


def test_unsigned_or_badly_signed_is_refused(billed: TestClient) -> None:
    body = b'{"meta":{}}'
    assert billed.post(URL, content=body).status_code == 403
    assert billed.post(URL, content=body, headers={"X-Signature": "00" * 32}).status_code == 403
    assert _plan(billed) == "free"


def test_lifecycle_cancel_keeps_pro_until_expired(billed: TestClient) -> None:
    org = _org_id(billed)
    assert _send(billed, org, "subscription_created", "active", "2026-11-01T10:00:00Z").json()["ok"]
    assert _plan(billed) == "pro"
    _send(billed, org, "subscription_cancelled", "cancelled", "2026-11-05T10:00:00Z")
    assert _plan(billed) == "pro"  # paid until the period ends (refund policy)
    _send(billed, org, "subscription_expired", "expired", "2026-12-01T10:00:00Z")
    assert _plan(billed) == "free"


def test_stale_and_replayed_events_are_ignored(billed: TestClient) -> None:
    org = _org_id(billed)
    _send(billed, org, "subscription_expired", "expired", "2026-12-01T10:00:00Z")
    late = _send(billed, org, "subscription_created", "active", "2026-11-01T10:00:00Z").json()
    assert late["ignored"] and _plan(billed) == "free"
    again = _send(billed, org, "subscription_expired", "expired", "2026-12-01T10:00:00Z").json()
    assert again["ignored"]


def test_payment_and_order_events_never_change_the_plan(billed: TestClient) -> None:
    org = _org_id(billed)
    _send(billed, org, "subscription_created", "active", "2026-11-01T10:00:00Z")
    r = _send(
        billed,
        org,
        "subscription_payment_success",
        "paid",
        "2026-11-02T10:00:00Z",
        "subscription-invoices",
    )
    assert r.json()["ignored"]
    _send(billed, org, "order_created", "paid", "2026-11-03T10:00:00Z", "orders")
    assert _plan(billed) == "pro"


def test_unknown_org_and_bad_json(billed: TestClient) -> None:
    assert _send(billed, 999999, "subscription_created", "active", "2026-11-01T10:00:00Z").json()[
        "ignored"
    ]
    assert _send(billed, "abc", "subscription_created", "active", "2026-11-01T10:00:00Z").json()[
        "ignored"
    ]
    body = b"not json"
    sig = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    assert billed.post(URL, content=body, headers={"X-Signature": sig}).status_code == 422


def test_checkout_link_is_url_encoded(cloud: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BILLING_PROVIDER", "lemonsqueezy")
    monkeypatch.setenv("LEMONSQUEEZY_CHECKOUT_URL", "https://shop.example/checkout/buy/abc")
    get_settings.cache_clear()
    h = signup(cloud, "a+b@example.com")
    url = cloud.post("/api/v1/billing/upgrade", json={"plan": "pro"}, headers=h).json()[
        "checkout_url"
    ]
    assert url.startswith("https://shop.example/checkout/buy/abc?")
    assert "a%2Bb%40example.com" in url and "checkout%5Bcustom%5D%5Borg_id%5D=" in url
