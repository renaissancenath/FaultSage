"""Plans and limits (D-017, Q-005). Values here are the single source for limits and the
pricing page. Change them by decision, not in code elsewhere."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class Plan:
    id: str
    name: str
    price_usd_month: int
    projects: int
    events_per_month: int
    retention_days: int
    seats: int
    features: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        d = asdict(self)
        d["features"] = list(self.features)
        return d


PLANS: dict[str, Plan] = {
    "free": Plan(
        "free",
        "Free",
        0,
        projects=2,
        events_per_month=5_000,
        retention_days=14,
        seats=1,
        features=(
            "Local CLI and dashboard",
            "Production error capture (SDK)",
            "Triage notes with draft regression tests",
            "Case file sync from the CLI",
        ),
    ),
    "pro": Plan(
        "pro",
        "Pro",
        12,
        projects=20,
        events_per_month=250_000,
        retention_days=90,
        seats=10,
        features=(
            "Everything in Free",
            "Team members with viewer and maintainer roles",
            "90 days of history",
            "Priority email support",
        ),
    ),
}


def plan(plan_id: str) -> Plan:
    return PLANS.get(plan_id, PLANS["free"])
