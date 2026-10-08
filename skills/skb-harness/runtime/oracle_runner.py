"""Oracle function loader and runner.

SPEC: skb-harness-SPEC §10. Oracle 탐색 순서 (먼저 찾은 것이 이긴다):
  1) <repo>/harness/oracle/<name>.py          — 소비자 저장소의 재정의
  2) skb-harness/oracle/<name>.py             — 하네스 기본 제공
  3) <skills>/*/oracle/<name>.py              — 형제 스킬이 제공하는 oracle (이름순)

2026-10-08 이전에는 3) 이 없어서 스킬이 제공한 oracle(evidence_seed_readiness 등)이 한 번도 로드되지 않았고,
workflow 가 요구한 oracle 6개 중 5개가 `function_not_found` 로 score 1.0 통과(vacuous PASS)했다.
oracle 함수는 `evaluate(target, run_context=None, ...)` 규약을 따르되, 로더는 함수가 받는 인자만 넘긴다.
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
from typing import Any, Callable, Iterator


def _load(path: Path, name: str) -> Callable[..., dict] | None:
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(f"skb_oracle_{name}", path)
    if not spec or not spec.loader:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fn = getattr(module, "evaluate", None)
    return fn if callable(fn) else None


def candidate_paths(target: Path, oracle_name: str, skills_dir: Path | None = None) -> Iterator[Path]:
    yield target / "harness" / "oracle" / f"{oracle_name}.py"
    here = Path(__file__).resolve()
    yield here.parents[1] / "oracle" / f"{oracle_name}.py"
    root = skills_dir if skills_dir is not None else here.parents[2]
    own = (here.parents[1] / "oracle").resolve()
    for d in sorted(root.glob("*/oracle")):
        if d.resolve() != own:
            yield d / f"{oracle_name}.py"


def _call(fn: Callable[..., dict], target: Path, run_context: dict[str, Any]) -> dict:
    """함수가 받는 인자만 넘긴다. **kwargs 를 받으면 모두 넘긴다."""
    params = inspect.signature(fn).parameters
    available = {"target": target, "run_context": run_context}
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return fn(**available) or {}
    return fn(**{k: v for k, v in available.items() if k in params}) or {}


def run_oracle(target: Path, oracle_name: str | None, run_context: dict[str, Any], skills_dir: Path | None = None) -> dict[str, Any]:
    """Return {'score': float, 'passed': bool, 'details': dict, 'oracle': name}.

    oracle 이 지정되지 않으면 benign 기본값(score=1.0)이다. 지정됐는데 찾지 못하면 같은 기본값을 돌려주되
    details 에 `skipped=function_not_found`, `searched`, `warning` 을 남겨 vacuous PASS 가 기록에서 보이게 한다.
    임계값 비교와 gate 판정은 orchestration 의 몫이고 하네스는 기록만 한다.
    """
    if not oracle_name:
        return {"oracle": None, "score": 1.0, "passed": True, "details": {"skipped": "no_oracle"}}

    searched = [p for p in candidate_paths(Path(target), oracle_name, skills_dir)]
    fn = None
    for p in searched:
        fn = _load(p, oracle_name)
        if fn is not None:
            break
    if fn is None:
        return {
            "oracle": oracle_name,
            "score": 1.0,
            "passed": True,
            "details": {
                "skipped": "function_not_found",
                "warning": "oracle not found; this PASS is vacuous",
                "searched": [str(p) for p in searched],
            },
        }
    try:
        result = _call(fn, Path(target), run_context)
    except Exception as exc:  # noqa: BLE001
        return {"oracle": oracle_name, "score": 0.0, "passed": False, "details": {"error": str(exc)}}
    score = float(result.get("score", 0.0))
    details = result.get("details")
    if details is None:  # 규약의 details 가 없는 oracle 은 score·passed 외 나머지를 details 로 본다
        details = {k: v for k, v in result.items() if k not in ("score", "passed")}
    return {
        "oracle": oracle_name,
        "score": score,
        "passed": bool(result.get("passed", False)),
        "details": details,
    }
