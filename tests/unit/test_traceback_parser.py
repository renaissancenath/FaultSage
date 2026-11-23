from __future__ import annotations

from faultsage.analysis.traceback_parser import parse_any, parse_cpython, parse_pytest

CHAINED = """Traceback (most recent call last):
  File "/app/src/load.py", line 10, in read
    return cfg["path"]
KeyError: 'path'

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/app/src/main.py", line 3, in <module>
    run()
  File "/app/src/main.py", line 7, in run
    read({})
  File "/app/src/load.py", line 12, in read
    raise RuntimeError("config incomplete") from exc
RuntimeError: config incomplete
"""


def test_parse_chained_cause() -> None:
    exc = parse_cpython(CHAINED, lambda p: p.startswith("/app/src"))
    assert exc is not None
    assert exc.type == "RuntimeError"
    assert exc.message == "config incomplete"
    assert [f.line for f in exc.frames] == [3, 7, 12]
    assert exc.cause is not None and exc.cause.type == "KeyError"
    assert exc.frames[-1].is_project


def test_parse_context_chain() -> None:
    text = CHAINED.replace(
        "The above exception was the direct cause of the following exception:",
        "During handling of the above exception, another exception occurred:",
    )
    exc = parse_cpython(text)
    assert exc is not None and exc.context is not None and exc.cause is None


def test_parse_windows_paths_and_caret_lines() -> None:
    text = (
        "Traceback (most recent call last):\n"
        '  File "C:\\code\\proj\\app.py", line 5, in main\n'
        "    x = 1 / 0\n"
        "        ~~^~~\n"
        "ZeroDivisionError: division by zero\n"
    )
    exc = parse_cpython(text)
    assert exc is not None and exc.frames[0].file_path == "C:\\code\\proj\\app.py"
    assert exc.frames[0].code == "x = 1 / 0"


def test_parse_pytest_long_format() -> None:
    text = """    def test_fit():
>       assert build_matrix(rows) == []

tests/test_train.py:5:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

    def build_matrix(rows):
>       return [r["transaction_amount"] for r in rows]
E       KeyError: 'transaction_amount'

src/churn/train.py:6: KeyError"""
    exc = parse_pytest(text)
    assert exc is not None
    assert exc.type == "KeyError"
    assert [(f.file_path, f.line) for f in exc.frames] == [
        ("tests/test_train.py", 5),
        ("src/churn/train.py", 6),
    ]


def test_edge_empty_or_garbage_returns_none() -> None:
    # edge_: hand-written input for a parser edge case real data does not cover.
    assert parse_any("") is None
    assert parse_any("nothing to see here\n\x00\xff") is None


def test_separate_failures_are_not_chained() -> None:
    log = (
        "ERROR: test_a\nTraceback (most recent call last):\n"
        '  File "/r/a.py", line 1, in f\n    x()\nKeyError: "a"\n\n'
        "ERROR: test_b\nTraceback (most recent call last):\n"
        '  File "/r/b.py", line 2, in g\n    y()\nValueError: b\n'
    )
    exc = parse_cpython(log)
    assert exc is not None and exc.type == "KeyError"
    assert exc.context is None and exc.cause is None
