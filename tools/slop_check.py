"""FaultSage anti-slop checker.

Scans UI code, tokens and docs for patterns banned by docs/DESIGN_SYSTEM.md
and prints findings as file:line. Exit code 1 if anything is found.

Usage:
    python tools/slop_check.py [PATHS...]          # default: web design docs README.md
    python tools/slop_check.py --contrast          # check token contrast ratios
"""

from __future__ import annotations

import argparse
import colorsys
import re
import sys
from pathlib import Path

CODE_EXT = {".css", ".scss", ".ts", ".tsx", ".js", ".jsx", ".html", ".vue", ".svelte"}
DOC_EXT = {".md"}
SKIP_DIRS = {"node_modules", "dist", "build", ".git", ".venv", "__pycache__"}
TOKENS_FILE = "tokens.css"
SPACE_SCALE = {0, 1, 4, 8, 12, 16, 24, 32, 48, 64}

CODE_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("gradient", re.compile(r"(linear|radial|conic)-gradient\s*\(", re.I)),
    ("glassmorphism / backdrop blur", re.compile(r"backdrop-filter|backdrop-blur", re.I)),
    ("banned font", re.compile(r"\b(Inter|Space Grotesk|Instrument Serif)\b")),
    ("lucide icons", re.compile(r"lucide", re.I)),
    ("pill radius", re.compile(r"border-radius\s*:\s*(9{3,}px|100px)|rounded-full", re.I)),
    ("all-caps text", re.compile(r"text-transform\s*:\s*uppercase|\buppercase\b", re.I)),
    ("opacity transition / fade", re.compile(r"transition[^;]*opacity|fade-?in|fadeIn", re.I)),
    ("animation", re.compile(r"@keyframes|animation\s*:(?!\s*none)", re.I)),
    ("bounce", re.compile(r"bounce", re.I)),
    # Lookaheads sit right after the colon so "\s*" cannot backtrack past the space.
    ("glow shadow", re.compile(r"box-shadow\s*:(?!\s*(?:none|var\(--fs-))", re.I)),
    ("text glow", re.compile(r"text-shadow\s*:(?!\s*none)", re.I)),
    ("raw HTML injection", re.compile(r"dangerouslySetInnerHTML|innerHTML\s*=")),
    ("lorem ipsum", re.compile(r"lorem ipsum", re.I)),
    (
        "buzzword",
        re.compile(
            r"\b(seamless(ly)?|supercharge|revolutionary|cutting-edge|unleash|effortless(ly)?|"
            r"game-?changing|next-gen|AI-powered|blazing)\b",
            re.I,
        ),
    ),
    ("em dash in copy", re.compile("\u2014")),
]
DOC_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("em dash", re.compile("\u2014")),
]
EMOJI = re.compile(
    "[\U0001f300-\U0001faff\U00002600-\U000027bf\U0001f000-\U0001f2ff\U0001f900-\U0001f9ff]"
)
HEX = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
# (?<![\w-]) keeps border-left-width or border-bottom from counting as spacing.
SPACING_PX = re.compile(
    r"(?<![\w-])(margin|padding|gap|row-gap|column-gap|top|left|right|bottom|inset)"
    r"(-[a-z]+)?\s*:\s*([^;]+);",
    re.I,
)
PX = re.compile(r"(-?\d+(?:\.\d+)?)px")


def is_purple(hex_value: str) -> bool:
    h = hex_value.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
    hue, light, sat = colorsys.rgb_to_hls(r, g, b)
    return 250 <= hue * 360 <= 320 and sat > 0.25 and 0.1 < light < 0.95


def iter_files(paths: list[Path]):
    for p in paths:
        if p.is_file():
            yield p
        elif p.is_dir():
            for f in p.rglob("*"):
                if f.is_file() and not (set(f.parts) & SKIP_DIRS):
                    yield f


def check_file(path: Path) -> list[str]:
    ext = path.suffix.lower()
    if ext not in CODE_EXT | DOC_EXT:
        return []
    findings: list[str] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    in_tokens = path.name == TOKENS_FILE
    for n, line in enumerate(text.splitlines(), 1):
        where = f"{path}:{n}"
        if ext in DOC_EXT:
            for name, rx in DOC_RULES:
                if rx.search(line):
                    findings.append(f"{where}: {name}")
            continue
        for name, rx in CODE_RULES:
            if in_tokens and name in {"glow shadow", "animation"}:
                continue
            if rx.search(line):
                findings.append(f"{where}: {name}: {line.strip()[:100]}")
        if EMOJI.search(line):
            findings.append(f"{where}: emoji")
        for hx in HEX.findall(line):
            if is_purple(hx):
                findings.append(f"{where}: purple/violet colour {hx}")
            elif not in_tokens and ext in {".css", ".scss"}:
                findings.append(f"{where}: raw hex {hx} (use a --fs- token)")
        if ext in {".css", ".scss"} and not in_tokens:
            for m in SPACING_PX.finditer(line):
                for v in PX.findall(m.group(3)):
                    if abs(float(v)) not in SPACE_SCALE:
                        findings.append(f"{where}: off-grid spacing {v}px (use --fs-space-*)")
    return findings


def _lum(hex_value: str) -> float:
    h = hex_value.lstrip("#")
    rgb = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def ratio(a: str, b: str) -> float:
    x, y = sorted((_lum(a), _lum(b)), reverse=True)
    return (x + 0.05) / (y + 0.05)


def check_contrast(tokens_path: Path) -> list[str]:
    css = tokens_path.read_text(encoding="utf-8")
    blocks = {
        "light": re.search(r":root\s*{(.*?)}", css, re.S),
        "dark": re.search(r'\[data-theme="dark"\]\s*{(.*?)}', css, re.S),
    }
    pairs = [
        ("fs-ink", "fs-paper", 4.5),
        ("fs-ink", "fs-surface", 4.5),
        ("fs-ink-2", "fs-paper", 4.5),
        ("fs-ink-2", "fs-surface", 4.5),
        ("fs-brand", "fs-paper", 4.5),
        ("fs-on-brand", "fs-brand", 4.5),
        ("fs-signal", "fs-paper", 4.5),
        ("fs-ok", "fs-paper", 4.5),
        ("fs-warn", "fs-paper", 4.5),
        ("fs-ink", "fs-signal-wash", 4.5),
        ("fs-rule-strong", "fs-paper", 3.0),
    ]
    out: list[str] = []
    for theme, m in blocks.items():
        if not m:
            out.append(f"{tokens_path}: missing {theme} block")
            continue
        vals = dict(re.findall(r"--(fs-[\w-]+)\s*:\s*(#[0-9A-Fa-f]{6})", m.group(1)))
        for fg, bg, need in pairs:
            if fg in vals and bg in vals:
                r = ratio(vals[fg], vals[bg])
                status = "ok  " if r >= need else "FAIL"
                print(f"{status} {theme:5} {fg} on {bg}: {r:.2f} (need {need})")
                if r < need:
                    out.append(f"{tokens_path}: {theme} {fg} on {bg} is {r:.2f}, needs {need}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--contrast", action="store_true")
    args = ap.parse_args()
    root = Path(__file__).resolve().parent.parent
    if args.contrast:
        findings = check_contrast(root / "design" / TOKENS_FILE)
    else:
        targets = [Path(p) for p in args.paths] or [
            root / "web",
            root / "design",
            root / "docs",
            root / "README.md",
            root / "AGENTS.md",
        ]
        findings = [f for file in iter_files(targets) for f in check_file(file)]
    for f in findings:
        print(f)
    print(f"\n{len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
