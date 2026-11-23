# 01 Security Rules

Each rule has an ID. PRs that touch the area must reference it. Tests in `tests/security/` cover the rules marked (T).

## Network and server
- **SR-1 (T)** Uvicorn binds to `127.0.0.1` only. Any other bind address is rejected at config load.
- **SR-2 (T)** Reject requests whose `Host` is not `127.0.0.1:<port>` or `localhost:<port>` (DNS rebinding defence).
- **SR-3 (T)** State-changing requests (POST, PUT, DELETE) and WebSocket upgrades require `Origin` equal to the dashboard origin. No CORS headers are sent; cross-origin requests fail.
- **SR-4 (T)** State-changing requests also require header `X-FaultSage-Request: 1` (cannot be set by plain cross-site forms).
- **SR-5** Security headers on every response: `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self' ws://127.0.0.1:* ws://localhost:*; frame-ancestors 'none'; base-uri 'none'; form-action 'self'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Cross-Origin-Opener-Policy: same-origin`.
- **SR-6 (T)** No outbound network calls during `init`, `watch`, `scan`, `run`, `verify`, `apply`, `dashboard`. Exceptions: optional Ollama on `127.0.0.1` when enabled, and `bench fetch`.

## Execution
- **SR-7 (T)** No `shell=True`, `os.system`, `eval`, `exec`, `compile` on external strings, `pickle`/`marshal` loads of untrusted data, `yaml.load` without SafeLoader. Enforced by Ruff S, Bandit, Semgrep.
- **SR-8 (T)** Verification runs only `sys.executable -m pytest <node ids>` where node ids come from recorded test events and match `^[\w./\\:\[\]-]+(::[\w\[\]\-.,= ]+)*$`, plus commands listed by the user in `verify.extra_commands`.
- **SR-9** Rule or model output is never executed. A model can propose a patch; it goes through the approval gate like any patch.
- **SR-10** Every subprocess has a timeout; process trees are killed on timeout.

## Files
- **SR-11 (T)** Only `fixes/apply_gate.py` writes to the monitored project. A test asserts unchanged file hashes across all other tests.
- **SR-12 (T)** Every path from config, events, patches or API is resolved (`Path.resolve(strict=False)`) and must be inside the project root; symlinks that resolve outside are refused.
- **SR-13 (T)** Patches apply only if base file hashes match; otherwise `patch_stale`.
- **SR-14 (T)** Apply requires a clean git tree or explicit stash confirmation, writes a backup first, and restores it on any failure.
- **SR-15** FaultSage data folder `.faultsage/` is created with user-only permissions where the OS supports it (0700 on POSIX; default user ACL on Windows).

## Data and output
- **SR-16 (T)** All text from projects passes through `faultsage.redact` before storage, display or export.
- **SR-17 (T)** The UI renders project text as text nodes only. No `dangerouslySetInnerHTML`, no Markdown rendering of untrusted text.
- **SR-18** Error responses never include stack traces or absolute paths outside the project.
- **SR-19** Logs contain ids and counts, never payloads.

## Dependencies and supply chain
- **SR-20** Python dependencies pinned in a lock file (`uv.lock` or `requirements-lock.txt` with hashes); JS in `package-lock.json`.
- **SR-21** pip-audit and npm audit must have no known high or critical issues at release.
- **SR-22** Fonts and all frontend assets are bundled locally. No CDN.
- **SR-23** GitHub Actions pinned to commit SHAs, `permissions: contents: read` by default.

## Benchmarks
- **SR-24** Benchmark repositories run only inside containers, as a non-root user, with network disabled after dependency install, CPU and memory limits, and a per-case timeout.
- **SR-25** Benchmark containers mount only the case folder, never the user's home or the FaultSage repo writable.

## Destructive actions
- **SR-26** Destructive DB migrations need `faultsage db migrate --approve <version>` and a fresh backup (DATABASE.md section 4).
- **SR-27** `purge` requires typed confirmation including the project name.
- **SR-28** AI agents must get human approval for each destructive call, every time (AGENTS.md section 5).
