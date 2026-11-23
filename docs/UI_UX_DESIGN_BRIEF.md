# FaultSage: UI/UX Design Brief

Reads with DESIGN_SYSTEM.md (tokens and components) and APP_FLOW.md (flows).

---

## 1. Who is looking at the screen

A developer or student in the middle of work, with a terminal open next to the browser. They glance at the dashboard after a failure. They want the answer in five seconds and the evidence in thirty. They may share a case file with a teammate or a non-technical lead.

## 2. The job of the interface

1. Say what broke in one sentence.
2. Show the most likely cause and why we think so.
3. Show what else it touched.
4. Offer one safe next action.
5. Prove the fix worked.

## 3. The one bright moment

On the **Case file** screen, the root-cause line in the code excerpt is highlighted with a vermilion bar, and the same vermilion traces the path on the graph from the root node to the failing test. That path is the only saturated colour on the screen. Everything else is ink on paper. This is the screenshot people will remember.

## 4. Screens

### 4.1 Overview
- **Headline:** the status line sentence ("Watching churn-pipeline since 14:02. 1 open incident.").
- **Open incidents table** (most recent first), max 10 rows, link to Incidents.
- **Last runs table:** last 5 pytest runs and `faultsage run` commands with result in words.
- **Project facts** as a two-column definition list: root, Python version, tests found, git branch and commit, signals on.
- Primary action: none when healthy. When there is an open incident: "Open case file".
- No stat banner, no charts for the sake of charts.

### 4.2 Incidents
- Table: ID, what failed, status, top cause certainty, first seen, last seen, occurrences.
- Filters as a single row of plain selects above the table. Search by file or test.
- Row click opens the case file. Keyboard: arrows move, Enter opens.

### 4.3 Case file (the main screen)
Wide layout, two columns:

**Left (7 columns)**
1. Headline: "test_fit failed: column transaction_amount is missing in train.py line 47" (32 px).
2. Meta line in mono: test id, file:line, first seen, occurrences.
3. **Likely causes**: ClaimRows ranked, each with certainty marker and word, one-line claim, "3 pieces of evidence" link that expands the EvidenceItems inline.
4. **Code excerpt** of the top cause with the highlighted line.
5. **Suggested fix**: explanation in two or three sentences, PatchDiff, verify command in mono with copy button.
6. Primary button: "Apply patch" (or "Run verification" after a fix is applied). Secondary links: "Copy patch", "Dismiss incident", "Export".

**Right (5 columns)**
1. **Propagation graph** (React Flow), fitted to the affected subgraph, with a "Show as list" toggle.
2. **Affected** ImpactList table.
3. **Timeline** of occurrences and actions.

If certainty is Unknown, the headline stays factual and the causes section opens with: "We do not have enough evidence to rank causes. Missing: coverage data, git history." with the command that would add it.

### 4.4 Pipeline
- Left-to-right graph of declared steps with StatusMarkers, plus a table view.
- Selecting a step shows its last checkpoint (columns, dtypes, shape) and related incidents.
- If no pipeline is declared: EmptyState with a short `pipeline.toml` example.

### 4.5 Scan
- "Run scan" primary button, then findings grouped by file in a table with severity word, rule, line, message.
- Each finding links to the file location.

### 4.6 Evaluation
- Table of benchmark run records: run id, dataset, version, split, attempted, reproduced, excluded.
- Selecting a run shows metrics with baselines side by side in a plain table, and per-case results with filters (correct, wrong, unknown).
- A small horizontal bar chart (SVG, no library) for Top-1/3/5 of FaultSage vs baselines is allowed here, flat colours, direct labels, no legend hunt.
- This page only shows real runs. If there are none: "No benchmark runs yet. Run faultsage bench run bugsinpy --split dev."

### 4.7 Settings
- Signals with on/off switches (with text "on"/"off"), log paths, retention days, port, optional local model.
- Danger area at the bottom, plain text with a rule above: "Purge local data". Opens a ConfirmDialog that lists what is deleted.

## 5. Layout and interaction rules

- Left-aligned 12-column grid, max 1280 px, 32 px page padding.
- One primary button per screen.
- No modals except ConfirmDialog for writes and deletes.
- No toasts. Results appear inline where the action happened and stay.
- No animation. Live updates replace content in place; a polite live region announces "New incident I-43: test_load failed".
- All times shown in the user's local time, with relative time in brackets ("14:02 (5 min ago)").
- Copy is specific and short. No marketing language inside the app.

## 6. Public project page (for portfolio, later)

A single static page in the repository (GitHub Pages, free for public repos).

- Headline: "Find the line that broke your Python project, and what else it broke."
- Under it, one sentence: "FaultSage is a free, local CLI and dashboard. It ranks likely causes with evidence, maps the blast radius and checks your fix."
- One primary action: "View on GitHub". Secondary text link: "Read the evaluation".
- A real screenshot of the case file screen (taken by Playwright from a real BugsInPy case).
- A results table copied from the latest test-split run record, with the run id and the number of reproduced cases.
- A 3-step "How it works" as a numbered list with commands, not three icon boxes.
- No testimonials, no company logos, no badges above the headline, no stat banner.

## 7. Screenshot and review loop

1. Every screen has a Playwright script in `tests/e2e/screens/` that loads real recorded data and saves screenshots at 1440, 1024, 768 and 375 px in light and dark.
2. The coding agent must look at these screenshots before marking UI work done.
3. Review order for every UI pull request: build with the Frontend Design skill direction, style with Taste Skill and UI UX Pro Max (constrained by our tokens), then check with Impeccable and Vercel Web Design Guidelines, then run `tools/slop_check.py`. Fix every finding or record why it does not apply.

## 8. Success for the UI

- A first-time user can say what broke and what to do next within 10 seconds of opening a case file (tested with at least 5 people, notes kept).
- Every screen passes axe-core with zero serious or critical issues.
- `tools/slop_check.py` passes.
- Screenshots show no banned pattern from DESIGN_SYSTEM.md section 2.
