---
name: faultsage-design
description: Use for any FaultSage UI work (dashboard screens, components, CSS, copy, the public project page). Enforces FaultSage tokens, spacing, component conventions and the anti-slop rules, and requires screenshots before UI work is called done.
---

# FaultSage design skill

You are building UI for FaultSage, a local tool that diagnoses Python failures. The look is an investigator's case file: warm paper, ink text, ruled tables, mono code, and one vermilion path for the thing that broke.

## Read first
1. `docs/DESIGN_SYSTEM.md` (all of it)
2. `design/tokens.css`
3. `docs/UI_UX_DESIGN_BRIEF.md` for the screen you are touching

## Tokens only
- Colours: `var(--fs-*)` only. No hex values in component CSS.
- Spacing: `--fs-space-1` to `--fs-space-8` (4, 8, 12, 16, 24, 32, 48, 64). No other px values for margin, padding, gap.
- Radius: `--fs-radius-0|1|2` (0, 2, 4). Never `9999px`, never `50%` except a status circle marker.
- Type: `--fs-text-*` sizes, IBM Plex Sans for UI, IBM Plex Mono for code, paths, ids and numbers.

## Component conventions
- Lists of things are `DataTable`. Cards only for one complete statement.
- Status = shape marker + word. Certainty = Confirmed, Strong, Possible, Unknown markers + word.
- One `Button.primary` per screen. Other actions are text buttons or links.
- Untrusted text (tracebacks, logs, code, file names) is rendered as text. Never `dangerouslySetInnerHTML`.
- `--fs-signal` appears only on the failure path. If you use it anywhere else, you are wrong.
- Every component has loading, empty, error and stale states written as specific sentences.

## Never
Purple or purple-to-blue gradients, any gradient, gradient text, glow, blobs, grain, glassmorphism or backdrop blur, Inter, Space Grotesk, Instrument Serif, italic serif accents, emoji anywhere in UI, Lucide, icons in boxes, three equal cards in a row, coloured-border cards, badges or pills above headlines, stat banners, tiny all-caps labels, pill-shaped everything, fade-in on scroll, bouncing, cursor beams, opacity or fade on hover, centred layouts, three competing buttons, fake testimonials or logos, lorem ipsum, builder leftovers, buzzwords (seamless, supercharge, unleash, effortless, AI-powered, next-gen, magic), em dashes in copy, low-contrast dark mode, untouched component-kit styles.

## Always
- Left-aligned 12-column grid, max 1280 px.
- A specific headline that says what happened or what the product does.
- Real data from recorded benchmark fixtures in previews and screenshots. No invented numbers.
- Keyboard access, visible focus ring, semantic HTML, WCAG 2.2 AA contrast.

## Workflow for every UI change
1. State the screen, the user's question it answers, and the one primary action.
2. Sketch the layout in a short text outline before code.
3. Build with tokens and existing components. New component? Add it to DESIGN_SYSTEM.md section 7 in the same PR.
4. Run `python tools/slop_check.py web design docs` and fix every hit.
5. Run the Playwright screen script for the screen; open and look at the screenshots at 1440, 768 and 375 px, light and dark.
6. Review with Impeccable (critique, audit) and Vercel Web Design Guidelines (file and line findings). Fix or record why not.
7. Attach screenshots to the PR.
