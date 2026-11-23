# FaultSage

**Finds the line that broke your Python project, shows what else it broke, and checks your fix.**

[![ci](https://img.shields.io/github/actions/workflow/status/renaissancenath/FaultSage/ci.yml?branch=main&style=for-the-badge&label=CI&logo=githubactions&logoColor=white)](https://github.com/renaissancenath/FaultSage/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![React](https://img.shields.io/badge/React-18-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)

![Ruff](https://img.shields.io/badge/lint-Ruff-D7FF64?style=for-the-badge&logo=ruff&logoColor=black)
![mypy](https://img.shields.io/badge/types-mypy-2A6DB2?style=for-the-badge)
![Security](https://img.shields.io/badge/security-Bandit%20%C2%B7%20Semgrep%20%C2%B7%20gitleaks-7B42BC?style=for-the-badge)
![a11y](https://img.shields.io/badge/a11y-axe--core-663399?style=for-the-badge)
![Licence](https://img.shields.io/badge/licence-all%20rights%20reserved-555555?style=for-the-badge)

<p align="center">
  <img src="docs/images/demo.gif" width="860" alt="Sign up, create a project and API key, a production error arrives triaged, and a case file from the CLI">
</p>

| | |
|---|---|
| **Local tool** | CLI + dashboard on `127.0.0.1`. Analysis, patches and verification run on your machine. |
| **FaultSage Cloud** | Accounts, workspaces, production error capture, triage notes. Free plan. |
| **Status** | Built and tested end to end locally. Deploy steps: [docs/LAUNCH.md](docs/LAUNCH.md). |

---

## How it works

![Case file in the local dashboard](web/public/screens/case-file.png)

```mermaid
flowchart LR
    subgraph P["Your project"]
        T["pytest / scripts / pipelines"]
        G["git history"]
    end
    subgraph L["FaultSage (local)"]
        C["Collectors<br/>pytest plugin · run wrapper · log tail"]
        S[("Spool<br/>JSONL")]
        D["Daemon"]
        E["Engine<br/>rank causes"]
        B["Blast radius<br/>import + pipeline graph"]
        F["Fix rules"]
        A{{"Apply gate<br/>typed approval"}}
        V["Verify<br/>rerun tests"]
        DB[("SQLite")]
        UI["Dashboard"]
    end
    T --> C --> S --> D --> E --> B
    G --> E
    E --> F --> A --> V
    D --> DB --> UI
    A -. "writes only after approval" .-> P
```

## System architecture

```mermaid
flowchart TB
    subgraph Dev["Developer machine"]
        CLI["faultsage CLI + daemon"]
        LUI["Local dashboard<br/>React"]
        LDB[("SQLite")]
        CLI --- LDB --- LUI
    end
    subgraph Prod["Customer's production app"]
        SDK["faultsage.sdk<br/>redacts before sending"]
    end
    subgraph Cloud["FaultSage Cloud (Docker · Render)"]
        API["FastAPI<br/>auth · CSRF · rate limits"]
        WEB["React app<br/>served by the same image"]
        TRI["Triage agent<br/>traceback-only"]
        PG[("PostgreSQL · Neon<br/>org_id on every row")]
        API --- PG
        API --- TRI
        WEB --- API
    end
    subgraph GH["GitHub"]
        CI["Actions<br/>CI · Friday check · triage"]
        ISS["Issues"]
    end
    CLI -- "case files, no source code" --> API
    SDK -- "API key · HTTPS" --> API
    TRI -- "issue link" --> ISS
    ISS --> CI
```

## Customer data isolation

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant A as FastAPI
    participant R as Repository layer
    participant D as PostgreSQL
    B->>A: GET /api/v1/projects/42 (session cookie)
    A->>A: session valid? CSRF on writes
    A->>A: resolve workspace from the user's memberships only
    A->>R: project(org_id, 42)
    R->>D: SELECT ... WHERE id = 42 AND org_id = :org
    D-->>R: no row (belongs to another workspace)
    R-->>A: None
    A-->>B: 404 Project not found
```

Every route with an id is called with another tenant's ids in [`tests/cloud/test_isolation.py`](tests/cloud/test_isolation.py); the test fails if a new route is added without being covered.

## Human approval for destructive actions

```mermaid
flowchart LR
    X["Destructive action<br/>patch · DROP migration · restore"] --> Q{"Typed confirmation<br/>+ named approver"}
    Q -- no --> N["Refused<br/>nothing changes"]
    Q -- yes --> K["Backup first<br/>fail closed"]
    K --> R["Run in one transaction"]
    R --> L[("Audit record<br/>who · what · backup")]
```

## Open core

```mermaid
flowchart TB
    subgraph Public["Public repository"]
        P1["CLI · daemon · dashboard"]
        P2["Cloud service · web app"]
        P3["Built-in engine<br/>traceback ranking"]
        P4["Benchmark harness · results"]
    end
    subgraph Private["Private package: faultsage_engine"]
        X1["Ranking features + scoring"]
        X2["Trained weights"]
        X3["Full fix-rule library"]
        X4["Training"]
    end
    Private -. "loaded when installed" .-> Public
```

## Evaluation (held-out projects)

Real bugs from [BugsInPy](https://github.com/soarsmu/BugsInPy); projects split into dev (tuning) and test (never seen). Test run [`2026-11-23_bugsinpy_test_090824`](results/runs/2026-11-23_bugsinpy_test_090824/run.json), 19 reproduced bugs:

| Method | Top-1 | Top-3 | Top-5 |
|---|---|---|---|
| FaultSage | 0.11 | 0.37 | 0.58 |
| Top stack frame | **0.53** | 0.58 | 0.58 |
| Random | 0.07 | 0.21 | 0.33 |

On unseen projects the ranker trails the top-stack-frame baseline at Top-1, so its "Strong" label is switched off until a new held-out run earns it back. Fix verification was correct on 19 of 19. Details: [docs/EVALUATION.md](docs/EVALUATION.md).

## CI on every pull request

```mermaid
flowchart LR
    PR(["Pull request"]) --> Py["Python<br/>ruff · mypy · pytest"]
    PR --> PGt["Cloud tests<br/>on PostgreSQL"]
    PR --> Sec["Security<br/>bandit · semgrep · pip-audit · gitleaks"]
    PR --> Web["Web<br/>lint · types · tests · build"]
    Web --> E2E["Browser<br/>19 screens + axe · 15-step customer journey"]
    PR --> Dk["Docker image<br/>builds and answers /healthz"]
    Py & PGt & Sec & E2E & Dk --> M{{"Review + merge<br/>by a person"}}
```

## Stack

| Layer | Choice |
|---|---|
| Analysis | Python 3.12, AST, NetworkX, coverage.py, logistic regression |
| Local | Typer CLI, FastAPI on 127.0.0.1, SQLite (WAL) |
| Cloud | FastAPI, SQLAlchemy Core, PostgreSQL, Argon2id, GitHub OAuth |
| Web | React 18, TypeScript, Vite, React Flow, CSS Modules on design tokens |
| Ops | Docker, Render + Neon, GitHub Actions |

## Run it

```powershell
python -m pip install -e ".[dev]"
faultsage init ; faultsage watch        # dashboard at http://127.0.0.1:8765
faultsage-cloud serve                     # hosted part on http://localhost:8000
```

| Guide | |
|---|---|
| [LAUNCH.md](docs/LAUNCH.md) | GitHub, CI, Neon, Render, email, live check, step by step |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, boundaries, data flow |
| [DECISIONS.md](docs/DECISIONS.md) | Every design decision and open question |
| [SECURITY.md](docs/SECURITY.md) | Threat model and rules |
| [REQUIREMENTS_MAP.md](docs/REQUIREMENTS_MAP.md) | Where each requirement lives in the code |

## Not done yet

- Not deployed; GitHub CI runs on the first push ([LAUNCH.md](docs/LAUNCH.md)).
- Ranking accuracy on unseen projects is below the baseline; more varied dev projects are the next step.
- Payments are built but switched off until the legal pages are reviewed and a store is set up.

## Licence

All rights reserved, see [LICENSE](LICENSE). The ranking engine is a separate private package. Benchmark datasets keep their own licences. IBM Plex fonts: SIL OFL 1.1.
