"""Email over any SMTP server (D-015). Free options: your own mailbox's SMTP with an app
password, or a free-tier SMTP relay. Without SMTP, links are written to the server log so an
operator can still complete verification in development."""

from __future__ import annotations

import logging
import smtplib
import ssl
import threading
from email.message import EmailMessage

from faultsage.cloud.settings import get_settings

_log = logging.getLogger("faultsage.cloud.mail")
outbox: list[EmailMessage] = []  # last messages, for tests and the dev log


def send(to: str, subject: str, body: str) -> bool:
    s = get_settings()
    msg = EmailMessage()
    msg["From"] = s.smtp_from or "FaultSage <no-reply@localhost>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    outbox.append(msg)
    del outbox[:-50]
    if not s.smtp_enabled:
        _log.warning(
            "SMTP not configured. Email to %s not sent. Subject: %s\n%s", to, subject, body
        )
        return False

    def deliver() -> None:
        try:
            if s.smtp_port == 465:
                with smtplib.SMTP_SSL(
                    s.smtp_host, s.smtp_port, context=ssl.create_default_context(), timeout=20
                ) as c:
                    if s.smtp_user:
                        c.login(s.smtp_user, s.smtp_password)
                    c.send_message(msg)
            else:
                with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as c:
                    if s.smtp_starttls:
                        c.starttls(context=ssl.create_default_context())
                    if s.smtp_user:
                        c.login(s.smtp_user, s.smtp_password)
                    c.send_message(msg)
        except (OSError, smtplib.SMTPException):
            _log.exception("Sending email failed (subject: %s)", subject)

    threading.Thread(target=deliver, daemon=True).start()
    return True


def verification(to: str, link: str) -> bool:
    return send(
        to,
        "Confirm your FaultSage email",
        f"Open this link to confirm your email address:\n\n{link}\n\n"
        "The link works once and expires in 24 hours. If you did not sign up, ignore this email.",
    )


def reset(to: str, link: str) -> bool:
    return send(
        to,
        "Reset your FaultSage password",
        f"Open this link to choose a new password:\n\n{link}\n\n"
        "The link works once and expires in 1 hour. If you did not ask for this, ignore this email; "
        "your password has not changed.",
    )


def invite(to: str, org: str, link: str) -> bool:
    return send(
        to,
        f"You were invited to {org} on FaultSage",
        f"You were invited to join {org} on FaultSage.\n\nAccept: {link}\n\nThe link expires in 7 days.",
    )


def new_issue(to: str, project: str, title: str, link: str) -> bool:
    return send(
        to,
        f"[{project}] New production error: {title[:80]}",
        f"FaultSage captured a new error in {project}:\n\n{title}\n\nCase file and triage note: {link}",
    )
