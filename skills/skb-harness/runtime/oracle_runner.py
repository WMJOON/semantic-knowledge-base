"""Oracle function loader and runner.

SPEC: skb-harness-SPEC §10. Looks for `<repo>/harness/oracle/<name>.py`
first, falling back to the skill-provided oracle directory if any.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Callable


def _load(path: Path, name: str) -> Callable[..., dict] | None:
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(f"msm_oracle_{name}", path)
    if not spec or not spec.loader:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fn = getattr(module, "evaluate", None)
    return fn if callable(fn) else None


def run_oracle(target: Path, oracle_name: str | None, run_context: dict[str, Any]) -> dict[str, Any]:
    """Return {'score': float, 'passed': bool, 'details': dict, 'oracle': name}.

    When no oracle is configured or the function can't be located the result is
    a benign default (score=1.0, passed=True) so the run isn't penalised for an
    unspecified oracle. Threshold comparison and gate judgment belong to
    orchestration; harness only records.
    """
    if not oracle_name:
        return {"oracle": None, "score": 1.0, "passed": True, "details": {"skipped": "no_oracle"}}

    search_paths = [
        target / "harness" / "oracle" / f"{oracle_name}.py",
        Path(__file__).resolve().parents[1] / "oracle" / f"{oracle_name}.py",
    ]
    fn = None
    for p in search_paths:
        fn = _load(p, oracle_name)
        if fn is not None:
            break
    if fn is None:
        return {
            "oracle": oracle_name,
            "score": 1.0,
            "passed": True,
            "details": {"skipped": "function_not_found", "searched": [str(p) for p in search_paths]},
        }
    try:
        result = fn(target=target, run_context=run_context) or {}
    except Exception as exc:  # noqa: BLE001
        return {"oracle": oracle_name, "score": 0.0, "passed": False, "details": {"error": str(exc)}}
    return {
        "oracle": oracle_name,
        "score": float(result.get("score", 0.0)),
        "passed": bool(result.get("passed", False)),
        "details": result.get("details", {}),
    }
