"""``python -m faultsage``: same as the ``faultsage`` command (works when Scripts/ is not on PATH)."""

from faultsage.cli.main import app

app(prog_name="faultsage")
