# FaultSage: Code Style

Tools enforce most of this. When the tool and this doc disagree, fix the config so they agree.

## 1. Python

### Formatting and lint
- Ruff format (line length 100) and Ruff lint with rule sets: `E, F, W, I, B, UP, SIM, RUF, S, PTH, ANN, N, C4, PL` (S = bandit-style security rules).
- mypy `--strict` for `analysis`, `fixes`, `storage`, `api`, `models`. Other packages at least `--check-untyped-defs`.

### Structure
- `src/` layout. One responsibility per module. Modules under 400 lines; split when larger.
- Public functions have docstrings that say what, inputs, outputs, and raised errors in one short paragraph.
- No global mutable state except the daemon service object.

### Naming
| Thing | Style | Example |
|---|---|---|
| Modules, functions, variables | `snake_case` | `build_import_graph` |
| Classes, Pydantic models | `PascalCase` | `CaseFile` |
| Constants | `UPPER_SNAKE` | `DEFAULT_PORT` |
| Requirement links | comment `# FR-12` near the code that implements it | |
| Booleans | `is_`, `has_`, `should_` | `is_project_frame` |

### Types and data
- `from __future__ import annotations` in every module.
- Pydantic models at boundaries; `dataclass(frozen=True, slots=True)` inside the engine.
- No `Any` in public signatures. No `dict` blobs passed between layers when a model exists.
- `pathlib.Path` for paths; resolve and check containment with `faultsage.paths.inside_root()`.

### Errors
- Custom exceptions in `faultsage/errors.py`, each with `code`, `message`, `next_step`.
- Never `except Exception: pass`. Catch narrowly; if broad catching is required (pytest plugin), log and continue with a comment explaining why.
- User-facing messages: what failed, why if known, what to do. No blame, no jokes.

### Subprocess
```python
subprocess.run(
    ["git", "-C", str(root), "diff", "--unified=0", base, "--", rel_path],
    capture_output=True,
    text=True,
    timeout=30,
    check=False,
    shell=False,
)
```
Always list args, timeout, `shell=False`, explicit return-code handling.

### Logging
- stdlib `logging`, JSON formatter for the daemon, plain for CLI.
- Never log secrets, environment values, file contents or full payloads. Log ids and counts.

### SQL
- Only in `storage/`. Parameterised (`?`). Table and column names never from input.

### Tests
- `tests/unit/test_<module>.py`, function names `test_<behaviour>_<condition>`.
- Fixtures from real recorded data only, with provenance (see TESTING.md).

## 2. TypeScript and React

- TypeScript `strict: true`, `noUncheckedIndexedAccess: true`.
- Biome for lint and format.
- Function components, hooks, no class components. Files: `PascalCase.tsx` for components, `camelCase.ts` for utilities.
- API types generated from OpenAPI (`npm run gen:api`). Never hand-write response types.
- Data fetching through one small client in `web/src/api/` with typed errors.
- No `any`. No non-null `!` without a comment.
- Untrusted strings rendered as text only. `dangerouslySetInnerHTML` is banned (lint rule + slop check).
- No component kits (no shadcn, MUI, Chakra, Bootstrap). Our components live in `web/src/components/`.
- Scrollable code, diff and table regions get `tabIndex={0}` so keyboard users can scroll them (WCAG 2.1.1, axe `scrollable-region-focusable`). Biome's `noNoninteractiveTabindex` is off for that reason.

## 3. CSS

- CSS Modules per component, importing nothing but tokens from `design/tokens.css` via `var(--fs-*)`.
- No hex, rgb or hsl values outside `tokens.css`.
- Spacing only `--fs-space-*`. Radius only `--fs-radius-*`.
- No `transition`, `animation`, `@keyframes`, `backdrop-filter`, `text-transform: uppercase`, gradients.
- Layout with CSS grid and flexbox. No absolute positioning except overlays.
- `tools/slop_check.py` enforces these.

## 4. Copy (UI text and docs)

- Sentence case. Short sentences. Specific nouns (file names, test names, counts).
- No em dashes in UI strings. No buzzwords (list in DESIGN_SYSTEM.md section 1).
- Times with units ("2 h ago"), numbers with units ("7 tests").
- Certainty words are fixed: Confirmed, Strong, Possible, Unknown.

## 5. Git

- Branches: `feat/FR-xx-short-name`, `fix/short-name`, `docs/short-name`, `bench/short-name`.
- Commits: imperative, under 72 characters for the subject, body explains why. Reference requirement IDs.
- One logical change per PR. No generated files committed except `results/runs/*` and the built API types.
- `.gitignore`: `.venv/`, `node_modules/`, `web/dist/`, `data/`, `.faultsage/`, `*.db`, `.env*`.

## 6. Comments

- Explain why, not what.
- Mark incomplete code with `# TODO(FR-xx): what is missing` and an issue link. No silent stubs.
