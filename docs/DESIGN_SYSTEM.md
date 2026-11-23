# FaultSage: Design System

Source of truth for tokens: `design/tokens.css`. This document explains them. If the two disagree, fix the disagreement in the same pull request.

---

## 1. Brand identity

| Item | Value |
|---|---|
| Name | FaultSage (one word, capital F and S) |
| What it is | A local tool that finds why a Python project broke and checks the fix |
| Personality | An investigator's case file: precise, calm, shows its evidence |
| Voice | Plain, specific, short. Says what happened, with file names and numbers. Admits uncertainty. |
| Logo | Wordmark "FaultSage" in IBM Plex Sans SemiBold, ink colour, plus a small mark: a square node with one line leaving it (the root cause and its first edge). No gear, no magnifying glass, no sparkles. |

### Voice rules

| Write | Do not write |
|---|---|
| "test_fit failed at train.py:47 because column transaction_amount is missing" | "Oops! Something went wrong" |
| "Strong: clean.py:31 renamed the column 2 hours ago" | "AI-powered root cause detected" |
| "We could not find the line. Source not available." | Guessing a line |
| "Apply patch" | "Supercharge your workflow" |
| Sentence case for all labels | ALL CAPS labels, Title Case Everywhere |

Banned words in UI and docs copy: seamless, supercharge, revolutionary, cutting-edge, unleash, effortless, magic, next-gen, AI-powered, game-changing, robust (as filler), blazing.

Punctuation: no em dashes in UI copy. Use a full stop, comma or colon.

---

## 2. Design direction

**The case file.** The dashboard reads like an investigator's notes laid on a desk: a warm paper ground, ink text, ruled tables, code set in mono, and one vivid colour reserved for the thing that broke and the path it travelled.

Principles:

1. **Evidence first.** Every claim sits next to its source (traceback, git diff, checkpoint, coverage).
2. **Left-aligned, asymmetric.** Content starts at the left edge of a column. Nothing centred except single-number cells and empty-state illustrations.
3. **Tables and timelines over cards.** Lists of things are tables. A card exists only when it holds one complete, specific statement.
4. **One bright moment per screen.** Vermilion is used only for the failure and its propagation path. On the case file, it lights the root-cause line in the code excerpt and the edges from root to failing test on the graph. Nothing else on the screen uses it.
5. **One primary action per screen.** Everything else is a text link or a quiet secondary button.
6. **Still by default.** No entrance animations, no scroll effects, no hover fades.

References to study (for structure, not to copy): a GitHub pull request diff view, Python's own traceback layout in docs.python.org, Datasette table pages, printed engineering notebooks with ruled lines.

### Anti-slop rules (hard rules, checked by `tools/slop_check.py` and review)

| # | Never | Instead |
|---|---|---|
| 1 | Purple, violet or purple-to-blue gradients | Flat colours from the palette |
| 2 | Gradient text, gradient hero | Solid ink text |
| 3 | Glow, neon, box-shadow halos | 1 px rules and one flat elevation shadow for overlays only |
| 4 | Glossy blobs, mesh gradients, grain over gradient | Plain paper background |
| 5 | Glassmorphism, backdrop blur | Solid surfaces |
| 6 | Inter everywhere, Space Grotesk + Instrument Serif, serif italic accents | IBM Plex Sans and IBM Plex Mono, upright |
| 7 | Emoji in headings, nav, buttons or labels | Phosphor icons (regular) only where they help, or text |
| 8 | Lucide icons everywhere, icon in a coloured box | Few icons, inline with text, no boxes |
| 9 | Three equal cards in a row, icon-box feature grids | Tables, ledgers, asymmetric two-column layouts |
| 10 | Coloured-border cards | Neutral 1 px border; status shown by marker and text |
| 11 | Badge or pill above a headline | Headline alone, specific |
| 12 | Stat banner of big vanity numbers | Numbers inside the table where they mean something |
| 13 | Tiny all-caps labels | Sentence case at 13 px minimum |
| 14 | Pill corners on everything | Radius scale in section 6 |
| 15 | Fade-in on scroll, bouncing, cursor-following beams, parallax | No motion except instant state changes |
| 16 | Buttons that fade or change opacity on hover | Background colour step on hover, no transition on opacity |
| 17 | Low-contrast dark mode, grey on grey | Dark theme tokens meet 4.5:1 for text |
| 18 | Untouched component kit styles (default shadcn look) | Our own components on our tokens |
| 19 | Fake reviews, testimonials, logos of companies that do not use it | Real screenshots of the real app |
| 20 | Generic buzzword headline | Headline that says what it does |
| 21 | Centred everything | Left-aligned grid |
| 22 | Three competing buttons | One primary, others as links |
| 23 | Builder leftovers (lorem ipsum, "Made with", default favicon, sample logos) | Real content only |
| 24 | Inconsistent spacing | 4-point scale only |
| 25 | Em dashes everywhere in copy | Shorter sentences |

---

## 3. Color palette

All colours are CSS custom properties in `design/tokens.css`. Contrast ratios were computed with the WCAG 2.x formula against the listed background and must be re-checked if a value changes (`tools/slop_check.py --contrast`).

### Light theme (default)

| Token | Hex | Use | Contrast |
|---|---|---|---|
| `--fs-paper` | `#F4F2ED` | Page background | n/a |
| `--fs-surface` | `#FBFAF7` | Panels, tables | n/a |
| `--fs-sunken` | `#ECE9E2` | Code blocks, table header | n/a |
| `--fs-ink` | `#16191D` | Primary text | 15.8:1 on paper |
| `--fs-ink-2` | `#4A5058` | Secondary text | 7.3:1 on paper |
| `--fs-rule` | `#CFCAC0` | Borders, table rules | decorative |
| `--fs-rule-strong` | `#8E8A82` | Input borders, focus-adjacent | 3.1:1 (non-text UI) |
| `--fs-brand` | `#0B5A5C` | Brand, primary button, links, selection | 7.1:1 on paper; paper text on brand 7.6:1 |
| `--fs-brand-hover` | `#08484A` | Primary button hover | |
| `--fs-signal` | `#C2410C` | **The bright moment only**: failure marker, root-cause line bar, propagation path | 4.6:1 on paper |
| `--fs-signal-wash` | `#FBE3D6` | Background of the highlighted root-cause line (text on it stays `--fs-ink`, 14.3:1; never signal text on wash) | n/a |
| `--fs-ok` | `#1F6B4A` | Passed, resolved (always with text) | 5.8:1 on paper |
| `--fs-warn` | `#8A5A00` | Warning (always with text) | 5.3:1 on paper |
| `--fs-focus` | `#0B5A5C` | Focus ring | 3:1+ against adjacent |
| `--fs-scrim` | ink at 48% (dark: black at 64%) | Backdrop behind ConfirmDialog only | n/a |
| `--fs-inset-rule` | 1 px inset ink | Active state of buttons | n/a |

### Dark theme

| Token | Hex | Contrast |
|---|---|---|
| `--fs-paper` | `#121518` | n/a |
| `--fs-surface` | `#1A1E22` | n/a |
| `--fs-sunken` | `#0E1113` | n/a |
| `--fs-ink` | `#ECEAE4` | 15.2:1 on paper |
| `--fs-ink-2` | `#B3B8BE` | 9.2:1 on paper |
| `--fs-rule` | `#343A40` | decorative |
| `--fs-rule-strong` | `#6B737B` | 3.8:1 |
| `--fs-brand` | `#5FC2BE` | 8.7:1 on paper |
| `--fs-signal` | `#FF8A50` | 7.9:1 on paper |
| `--fs-signal-wash` | `#3A2016` | n/a |
| `--fs-ok` | `#6FCF97` | 9.6:1 |
| `--fs-warn` | `#E8B44C` | 9.7:1 |

Rules:
- Signal colour appears on a screen only when there is a failure, and only on the failure path.
- Status never relies on colour alone: every status has a shape marker and a word.
- No gradients anywhere. No purple or violet hue anywhere (hue 250 to 320 is banned in tokens).

---

## 4. Typography

| Role | Font | Weights | Notes |
|---|---|---|---|
| UI and body | IBM Plex Sans | 400, 500, 600 | Upright only |
| Code, paths, ids, numbers in tables | IBM Plex Mono | 400, 500 | `font-variant-numeric: tabular-nums` |

Self-hosted WOFF2 in `web/public/fonts/` with `OFL.txt`. `font-display: swap`. Fallback stack: `"IBM Plex Sans", "Segoe UI", system-ui, sans-serif` and `"IBM Plex Mono", Consolas, ui-monospace, monospace`.

Type scale (px / line height):

| Token | Size | Line height | Weight | Use |
|---|---|---|---|---|
| `--fs-text-xs` | 13 | 20 | 400 | Table meta, captions (minimum size) |
| `--fs-text-sm` | 14 | 20 | 400 | Table body, secondary |
| `--fs-text-md` | 16 | 24 | 400 | Body |
| `--fs-text-lg` | 20 | 28 | 600 | Section headings |
| `--fs-text-xl` | 24 | 32 | 600 | Screen titles |
| `--fs-text-2xl` | 32 | 40 | 600 | Case file headline only |
| `--fs-code` | 13 | 20 | 400 mono | Code excerpts, tracebacks |

Rules: no all-caps text (except real acronyms like CLI, API). No letter-spacing tricks. No italic for decoration; italic only for quoting a user's own text. Max line length 72 characters for prose.

---

## 5. Spacing

4-point grid. Only these values are allowed for margin, padding, gap and positioning:

| Token | px |
|---|---|
| `--fs-space-1` | 4 |
| `--fs-space-2` | 8 |
| `--fs-space-3` | 12 |
| `--fs-space-4` | 16 |
| `--fs-space-5` | 24 |
| `--fs-space-6` | 32 |
| `--fs-space-7` | 48 |
| `--fs-space-8` | 64 |

Layout: 12-column grid, 24 px gutters, max content width 1280 px, left-aligned with 32 px page padding on wide screens and 16 px on small screens. Table row height 40 px (compact 32 px). Control height 36 px.

---

## 6. Border radius

| Token | px | Use |
|---|---|---|
| `--fs-radius-0` | 0 | Tables, code blocks, graph canvas |
| `--fs-radius-1` | 2 | Inputs, checkboxes, status markers |
| `--fs-radius-2` | 4 | Buttons, panels, dialogs |

Nothing is fully rounded. Status markers are circles only when the shape itself carries meaning (see section 7, status markers).

---

## 7. Components

Built in-house on tokens. No component kit.

| Component | Spec |
|---|---|
| **AppShell** | Left text nav (Overview, Incidents, Pipeline, Scan, Evaluation, Settings), 220 px wide, no icons in nav. Top status line across content area. |
| **StatusLine** | One sentence: "Watching churn-pipeline since 14:02. 1 open incident." plus Pause and Stop as text buttons. Paused state says "Paused" in words. |
| **DataTable** | 1 px horizontal rules, no vertical rules, header on `--fs-sunken`, sortable columns with text arrows, keyboard focusable rows, sticky header. Empty and error rows defined. |
| **CaseFileHeader** | Headline states the failure in one sentence (32 px), followed by test id, file:line and first-seen time in mono. |
| **ClaimRow** | Certainty marker + label + claim text + evidence count link. |
| **CertaintyMarker** | Confirmed: filled square. Strong: square with half fill. Possible: outlined square. Unknown: dashed outline square. Always followed by the word. |
| **StatusMarker** | Passed: filled circle + "passed". Failed: filled square in signal + "failed". Warning: triangle outline + "warning". Not run: outline circle + "not run". |
| **EvidenceItem** | Source label (traceback, git, checkpoint, coverage, log), stance (supports, contradicts), the excerpt in mono, link to open the file location. |
| **CodeExcerpt** | Mono, line numbers, 5 lines of context, root-cause line on `--fs-signal-wash` with a 3 px left bar in `--fs-signal`. Text only, never rendered as HTML. |
| **PropagationGraph** | React Flow canvas on `--fs-surface`, square nodes with labels, known edges solid ink-2, inferred edges dashed with "inferred" label, root-to-failure path in signal, 2 px. Keyboard navigable list view toggle. |
| **ImpactList** | Table of affected components: name, kind (module, step, test), direct or indirect, known or inferred. |
| **PatchDiff** | Unified diff, added lines with `+` and ok-tinted text, removed lines with `-`, no colour-only meaning. |
| **Button.primary** | `--fs-brand` background, paper text, radius 4, height 36. Hover: `--fs-brand-hover` instantly. No opacity change, no scale, no transition. One per screen. |
| **Button.secondary** | Text button in brand colour with underline on hover. |
| **ConfirmDialog** | Shows exactly what will change (files, diff) and requires an explicit confirm button labelled with the action ("Apply patch to 1 file"). |
| **Timeline** | Vertical list of occurrences and actions with timestamps in mono. |
| **Notice** | Inline message bar for errors and warnings with a marker and a sentence saying what failed and what to do next. No toasts that disappear. |
| **EmptyState** | One sentence saying why it is empty and the one command to change that, for example "No incidents yet. Run pytest while faultsage watch is running." |

Cards: allowed only when the card holds one complete statement (for example "Fix verified: 7 of 7 affected tests pass"). No decorative card grids.

---

## 8. Icons

- Phosphor Icons, regular weight, 16 px or 20 px, `currentColor`.
- Use an icon only when it adds meaning next to text: copy, external link, file, git commit, play (run verification), pause.
- Never an icon alone without an accessible label. Never icons in nav. Never icons inside coloured boxes or circles. Never emoji.
- Status uses the shape markers in section 7, not icons.

---

## 9. Responsive breakpoints

| Name | Min width |
|---|---|
| `sm` | 0 to 767 px (test at 375) |
| `md` | 768 px |
| `lg` | 1024 px |
| `xl` | 1280 px |

---

## 10. Responsive behaviour

- `xl` and `lg`: nav left, case file in two columns (claims and evidence 7 columns, graph and impact 5 columns).
- `md`: nav collapses to a top text menu; case file single column in this order: headline, likely causes, code excerpt, fix, graph, impact, timeline.
- `sm`: same order; tables scroll horizontally with a visible "scroll for more columns" hint; graph switches to list view by default with a link to open the graph.
- Nothing important is hidden on small screens. Touch targets at least 40 px.

---

## 11. States

Every data component defines all of these:

| State | Rule |
|---|---|
| Loading | Text "Loading incidents" with no spinner animation longer than needed; skeletons are plain rules, no shimmer |
| Empty | Sentence + one command or action |
| Success | Quiet inline confirmation that names the result |
| Warning | Warn marker + sentence + next step |
| Error | Says what failed, why if known, and the next action. No stack traces in the UI unless it is the user's own traceback being diagnosed |
| Stale | "File changed since this suggestion was made. Regenerate suggestion." |
| Paused | Status line says "Paused. New signals are queued and will be processed when you resume." |
| Disconnected | "Lost connection to the FaultSage daemon. Is faultsage watch still running?" with retry |
| Unknown certainty | Explicit "Unknown" claim with what evidence is missing |

Hover: background step or underline, instant. Focus: 2 px `--fs-focus` outline with 2 px offset, always visible. Active: 1 px inset rule. Disabled: `--fs-ink-2` text, `not-allowed` cursor, still readable.

---

## 12. Accessibility

- WCAG 2.2 AA target. Text contrast at least 4.5:1, large text and UI parts at least 3:1.
- Full keyboard use: nav, tables (arrow keys move row focus), graph (list view equivalent), dialogs (focus trap, Escape closes).
- Semantic HTML: `nav`, `main`, `table` with `th scope`, headings in order, `button` for actions, `a` for navigation.
- Live region announces new incidents politely.
- Status by shape and word, never colour alone.
- `prefers-reduced-motion` is irrelevant because there is no motion; keep it that way.
- Code excerpts are real text, selectable and readable by screen readers, with line numbers in a separate column hidden from copy.
- axe-core runs in Playwright on every screen in CI.
