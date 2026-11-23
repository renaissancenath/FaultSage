"""Fix rules that ship with the public package. The full rule library is part of the separately
installed engine (``faultsage_engine.rules``)."""

from __future__ import annotations

import difflib
import re

from faultsage.fixes.rules.base import Rule, RuleContext, explanation_only
from faultsage.models.core import Suggestion

_NO_MODULE = re.compile(r"No module named '(?P<mod>[\w.]+)'")

_CANNOT_IMPORT = re.compile(r"cannot import name '(?P<name>\w+)' from '(?P<mod>[\w.]+)'")

# Import name -> distribution name, for the common cases where they differ.
_DIST = {
    "sklearn": "scikit-learn",
    "cv2": "opencv-python",
    "yaml": "PyYAML",
    "PIL": "Pillow",
    "bs4": "beautifulsoup4",
    "dateutil": "python-dateutil",
    "dotenv": "python-dotenv",
}


class VersionConflictRule:
    rule_id = "version-conflict"

    def match(self, ctx: RuleContext) -> bool:
        return ctx.exception.type == "ImportError" and bool(
            _CANNOT_IMPORT.search(ctx.exception.message)
        )

    def suggest(self, ctx: RuleContext) -> Suggestion:
        m = _CANNOT_IMPORT.search(ctx.exception.message)
        name, mod = (m.group("name"), m.group("mod")) if m else ("?", "?")
        top = mod.split(".")[0]
        ver = ctx.installed_version(_DIST.get(top, top))
        installed = f"Installed {top} version: {ver}." if ver else f"{top} metadata was not found."
        return explanation_only(
            self.rule_id,
            ctx,
            f"{name!r} cannot be imported from {mod!r}. {installed} The name was probably added, moved or "
            f"removed in a different version. Check the {top} changelog for {name}, then pin the version "
            "your code expects in your dependency file.",
        )


class ImportRule:
    rule_id = "import-error"

    def match(self, ctx: RuleContext) -> bool:
        return ctx.exception.type in ("ModuleNotFoundError", "ImportError")

    def suggest(self, ctx: RuleContext) -> Suggestion:
        msg = ctx.exception.message
        m = _NO_MODULE.search(msg)
        if m:
            mod = m.group("mod")
            top = mod.split(".")[0]
            project_mods = sorted({n.split(".")[-1] for n in ctx.analysis.import_graph.nodes})
            close = difflib.get_close_matches(top, project_mods, n=1, cutoff=0.8)
            if close and close[0] != top:
                return explanation_only(
                    self.rule_id,
                    ctx,
                    f"No module named {mod!r}. Your project has a module called {close[0]!r}; this may be a "
                    "typo or a renamed module. Fix the import, then rerun.",
                )
            dist = _DIST.get(top, top)
            return explanation_only(
                self.rule_id,
                ctx,
                f"Module {mod!r} is not installed in the environment that ran this. Install it inside your "
                f"virtual environment with: python -m pip install {dist} and add it to your dependency file. "
                "FaultSage never installs packages for you.",
            )
        m2 = _CANNOT_IMPORT.search(msg)
        if m2:
            return VersionConflictRule().suggest(ctx)
        return explanation_only(self.rule_id, ctx, f"Import failed: {msg}")


class FileNotFoundRule:
    rule_id = "file-not-found"

    def match(self, ctx: RuleContext) -> bool:
        return ctx.exception.type == "FileNotFoundError"

    def suggest(self, ctx: RuleContext) -> Suggestion:
        rs = ctx.analysis.raise_site
        where = f" at {rs.file_path}:{rs.line}" if rs and rs.available else ""
        return explanation_only(
            self.rule_id,
            ctx,
            f"A file was not found{where}: {ctx.exception.message}. Relative paths are resolved from the "
            "current working directory, not from the script's folder. Build the path from "
            "Path(__file__).parent, or run the command from the project root.",
        )


RULES: list[Rule] = [VersionConflictRule(), ImportRule(), FileNotFoundRule()]
