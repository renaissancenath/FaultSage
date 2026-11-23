"""Copy bug reports sent by email into GitHub issues (RELEASE_AND_OPERATIONS.md section 4).

Reads unseen messages over IMAP (stdlib imaplib, TLS), strips personal data (addresses, phone
numbers, signature block), redacts secrets, and creates an issue labelled "bug" and "from-email"
with the gh CLI. Messages are marked seen only after the issue exists. Does nothing when the
BUG_IMAP_* variables are not set.
"""

from __future__ import annotations

import email
import imaplib
import os
import re
import subprocess
import sys
from email.message import Message

from faultsage.redact import redact

EMAIL_RX = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RX = re.compile(r"\+?\d[\d ()-]{7,}\d")


def body_text(msg: Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get_filename():
                payload = part.get_payload(decode=True)
                return (
                    payload.decode(part.get_content_charset() or "utf-8", "replace")
                    if isinstance(payload, bytes)
                    else ""
                )
        return ""
    payload = msg.get_payload(decode=True)
    return (
        payload.decode(msg.get_content_charset() or "utf-8", "replace")
        if isinstance(payload, bytes)
        else ""
    )


def clean(text: str) -> str:
    text = re.split(r"\n-- ?\n", text, maxsplit=1)[0]  # drop signature block
    text = "\n".join(
        line for line in text.splitlines() if not line.startswith(">")
    )  # drop quoted replies
    text = EMAIL_RX.sub("[email removed]", text)
    text = PHONE_RX.sub("[phone removed]", text)
    return redact(text)[:20_000]


def main() -> int:
    host, user, password = (
        os.environ.get(k, "") for k in ("BUG_IMAP_HOST", "BUG_IMAP_USER", "BUG_IMAP_PASSWORD")
    )
    if not (host and user and password):
        print("BUG_IMAP_* not configured; nothing to do.")
        return 0
    with imaplib.IMAP4_SSL(host) as box:
        box.login(user, password)
        box.select("INBOX")
        _, data = box.search(None, "UNSEEN")
        ids = data[0].split() if data and data[0] else []
        for mid in ids[:20]:
            _, parts = box.fetch(mid, "(BODY.PEEK[])")
            raw = parts[0][1] if parts and isinstance(parts[0], tuple) else b""
            msg = email.message_from_bytes(raw)
            subject = clean(str(msg.get("Subject", "Bug report")))[:200] or "Bug report"
            body = "Reported by email. Sender details removed.\n\n" + clean(body_text(msg))
            res = subprocess.run(
                [
                    "gh",
                    "issue",
                    "create",
                    "--title",
                    f"[email] {subject}",
                    "--body",
                    body,
                    "--label",
                    "bug",
                    "--label",
                    "from-email",
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if res.returncode == 0:
                box.store(mid, "+FLAGS", "\\Seen")
                print(f"Created {res.stdout.strip()}")
            else:
                print(f"Could not create issue: {res.stderr.strip()}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
