from __future__ import annotations

import pytest

from faultsage.redact import redact, redact_obj


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("key AKIAIOSFODNN7EXAMPLE used", "aws_access_key"),
        ("token ghp_" + "a" * 36, "github_token"),
        ("xoxb-1234567890-abcdefghij", "slack_token"),
        ("Authorization: Bearer abcdefghijklmnop123", "bearer"),
        ("jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N", "jwt"),
        ("password=hunter2hunter2", "secret"),
        ('{"api_key": "abc123def456"}', "secret"),
        ("-----BEGIN RSA PRIVATE KEY-----\nMIIabc\n-----END RSA PRIVATE KEY-----", "private_key"),
        ("fsk_" + "Z" * 40, "faultsage_key"),
    ],
)
def test_redact_masks_known_secret_formats(text: str, kind: str) -> None:
    out = redact(text)
    assert "[redacted:" in out
    assert "hunter2" not in out and "AKIAIOSFODNN7EXAMPLE" not in out


def test_redact_masks_secret_environment_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SERVICE_TOKEN", "s3cr3t-value-xyz")
    assert "s3cr3t-value-xyz" not in redact("connecting with s3cr3t-value-xyz now")


def test_redact_keeps_ordinary_text() -> None:
    text = "KeyError: 'transaction_amount' in train.py line 47"
    assert redact(text) == text


def test_redact_handles_none_and_caps_length() -> None:
    assert redact(None) == ""
    assert len(redact("a" * 300_000)) == 200_000


def test_redact_obj_recurses() -> None:
    data = redact_obj({"a": ["password=topsecret1"], "b": 3})
    assert data == {"a": ["password=[redacted:secret]"], "b": 3}


def test_redact_is_linear_on_hostile_input() -> None:
    import time

    start = time.monotonic()
    redact("password=" + "=" * 100_000 + "a" * 100_000)
    assert time.monotonic() - start < 2.0


def test_strip_source_drops_excerpts_and_patches_only() -> None:
    from faultsage.redact import strip_source

    data = {
        "title": "t",
        "hypotheses": [{"location": {"file_path": "a.py", "line": 1, "excerpt": [[1, "code"]]}}],
        "suggestions": [{"explanation": "e", "patch_diff": "+code"}],
    }
    out = strip_source(data)
    assert out == {
        "title": "t",
        "hypotheses": [{"location": {"file_path": "a.py", "line": 1, "excerpt": None}}],
        "suggestions": [{"explanation": "e", "patch_diff": None}],
    }
