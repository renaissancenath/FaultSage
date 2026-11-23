"""faultsage cloud login|push|status|logout: optional sync with FaultSage Cloud (D-014)."""

from __future__ import annotations

import typer

cloud_app = typer.Typer(
    help="Optional: sync redacted case files to FaultSage Cloud.", no_args_is_help=True
)


@cloud_app.command("login")
def login(
    url: str = typer.Option(
        ..., "--url", help="Your FaultSage Cloud address, e.g. https://faultsage.example.com"
    ),
    api_key: str = typer.Option(
        ...,
        "--api-key",
        prompt=True,
        hide_input=True,
        help="Project API key from Cloud > Settings > API keys.",
    ),
) -> None:
    """Store the API key in ~/.faultsage/cloud.json (user-only). Never in the project."""
    from faultsage.cloud_sync import save_credentials

    if not url.startswith(("https://", "http://127.0.0.1", "http://localhost")):
        typer.echo("Use an https:// address (plain http is only allowed for localhost).", err=True)
        raise typer.Exit(1)
    import httpx

    try:
        r = httpx.get(
            f"{url.rstrip('/')}/api/v1/ingest/whoami",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10.0,
        )
    except httpx.HTTPError as e:
        typer.echo(f"Could not reach {url}: {e}", err=True)
        raise typer.Exit(1) from e
    if r.status_code != 200:
        typer.echo(
            "The API key was refused. Create a new one in Cloud > Settings > API keys.", err=True
        )
        raise typer.Exit(1)
    path = save_credentials(url, api_key)
    info = r.json()
    typer.echo(
        f"Connected to project {info.get('project')} ({info.get('plan')} plan). Key saved in {path}."
    )
    typer.echo(
        "Turn on automatic sync with [cloud] enabled = true in .faultsage/config.toml, or push by hand:"
    )
    typer.echo("  faultsage cloud push I-1")


@cloud_app.command("push")
def push(
    incidents: list[str] = typer.Argument(..., help="Incident ids, e.g. I-1 I-2, or 'all'."),
) -> None:
    """Send redacted case files for these incidents. Source files never leave your machine."""
    from faultsage.cli.main import _id, _ingest_now, _paths, _workspace
    from faultsage.cloud_sync import load_credentials, push_incidents

    if load_credentials() is None:
        typer.echo("Not logged in. Run faultsage cloud login --url ... first.", err=True)
        raise typer.Exit(1)
    ws = _workspace(_paths())
    _ingest_now(ws)  # failures recorded without `faultsage watch` running are still in the spool
    ids = (
        [i.id for i in ws.list_incidents(None, None, 1000, None)[0]]
        if incidents == ["all"]
        else [_id(i) for i in incidents]
    )
    sent = push_incidents(ws, ids)
    typer.echo(f"Sent {sent} of {len(ids)} case file(s).")


@cloud_app.command("logout")
def logout() -> None:
    """Delete the stored API key."""
    from faultsage.cloud_sync import credentials_path

    p = credentials_path()
    if p.exists():
        p.unlink()
    typer.echo("Logged out of FaultSage Cloud.")
