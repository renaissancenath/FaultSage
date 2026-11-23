"""AST index (FR-16): line -> enclosing function and class; function signatures for rules."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class FunctionInfo:
    qualname: str
    name: str
    class_name: str | None
    start: int
    end: int
    min_args: int
    max_args: int | None  # None means *args
    params: tuple[str, ...]


@dataclass(slots=True)
class FileIndex:
    functions: list[FunctionInfo] = field(default_factory=list)
    syntax_error: str | None = None

    def enclosing(self, line: int) -> FunctionInfo | None:
        best: FunctionInfo | None = None
        for f in self.functions:
            if f.start <= line <= f.end and (best is None or f.start >= best.start):
                best = f
        return best

    def by_name(self, name: str) -> list[FunctionInfo]:
        return [f for f in self.functions if f.name == name or f.qualname == name]


def _arity(args: ast.arguments, is_method: bool) -> tuple[int, int | None, tuple[str, ...]]:
    positional = [*args.posonlyargs, *args.args]
    names = [a.arg for a in positional]
    if is_method and names and names[0] in ("self", "cls"):
        positional = positional[1:]
        names = names[1:]
    n_defaults = len(args.defaults)
    min_args = max(len(positional) - n_defaults, 0)
    max_args = None if args.vararg else len(positional)
    return min_args, max_args, tuple(names + [a.arg for a in args.kwonlyargs])


def index_source(source: str) -> FileIndex:
    idx = FileIndex()
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError) as exc:
        idx.syntax_error = str(exc)
        return idx

    def visit(node: ast.AST, stack: list[str], cls: str | None) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                visit(child, [*stack, child.name], child.name)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qual = ".".join([*stack, child.name])
                mn, mx, params = _arity(
                    child.args, is_method=cls is not None and stack[-1:] == [cls]
                )
                start = min([child.lineno, *(d.lineno for d in child.decorator_list)])
                idx.functions.append(
                    FunctionInfo(
                        qualname=qual,
                        name=child.name,
                        class_name=cls,
                        start=start,
                        end=child.end_lineno or child.lineno,
                        min_args=mn,
                        max_args=mx,
                        params=params,
                    )
                )
                visit(child, [*stack, child.name], None)
            else:
                visit(child, stack, cls)

    visit(tree, [], None)
    return idx


def excerpt(source: str, line: int, context: int = 5) -> list[tuple[int, str]]:
    lines = source.splitlines()
    lo = max(1, line - context)
    hi = min(len(lines), line + context)
    return [(n, lines[n - 1]) for n in range(lo, hi + 1)]
