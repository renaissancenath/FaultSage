# 02 Login Rules

## 1. Version 1: no accounts

FaultSage v1 is a single-user local tool. There are no usernames, passwords or sign-up. Authentication proves only one thing: **the browser talking to the dashboard was opened by the person who started `faultsage watch` on this machine.**

## 2. Session flow

1. `faultsage watch` generates a token: `secrets.token_urlsafe(32)` (256 bits).
2. The daemon keeps only `sha256(token)` in memory. The token is printed once in the terminal and written to `.faultsage/session` (user-only permissions) so `faultsage dashboard` can open the browser later.
3. The browser opens `http://127.0.0.1:8765/#t=<token>`. The token is in the URL fragment, so it is never sent in a request line or logged by the server.
4. The page reads the fragment, POSTs it to `/auth/session` once, then replaces the URL without the fragment.
5. The server compares hashes in constant time (`hmac.compare_digest`) and sets a cookie:
   `fs_session=<random session id>; HttpOnly; SameSite=Strict; Path=/` (no `Secure` flag because it is plain HTTP on loopback).
6. The one-time token is invalidated after first use. `faultsage dashboard` issues a new one.

## 3. Rules

- **LR-1** Session ids: 256-bit random, stored hashed in memory, never in the DB.
- **LR-2** Session lifetime ends when the daemon stops. Idle timeout 12 hours.
- **LR-3** Max 5 active sessions; oldest is dropped.
- **LR-4** `/auth/session` rate limited to 10 attempts per minute; then 60 second lockout. Failed attempts logged (count only).
- **LR-5** Every API and WebSocket request requires a valid session cookie plus the Host and Origin checks in 01_SECURITY-RULES.md.
- **LR-6** `faultsage stop` and `faultsage logout` revoke all sessions.
- **LR-7** Tokens never appear in logs, exports or error messages.
- **LR-8** Write actions (apply, purge, settings change) additionally require an explicit confirm step in the UI.

## 4. Future multi-user version (not built, rules fixed in advance)

If FaultSage ever runs as a shared server:
- Passwords hashed with Argon2id (argon2-cffi, MIT), memory cost at least 64 MB.
- Minimum length 12, check against a local breached-password list, no composition rules.
- Optional TOTP second factor (pyotp, MIT). No SMS.
- Lockout with exponential backoff after 5 failures; generic error messages ("email or password is wrong").
- HTTPS only, `Secure` cookies, CSRF tokens, session rotation on login and privilege change.
- Roles: viewer (read), maintainer (approve and apply). Apply always logged with user id.
- Account deletion removes personal data within 30 days.

These require a new decision in DECISIONS.md before any code is written.
