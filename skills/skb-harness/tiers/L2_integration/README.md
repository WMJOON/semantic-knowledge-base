# Tier L2 — Integration

L2 운영은 `runtime/dispatch.py`가 직접 수행한다. tier 진입점은:

```bash
runtime/run.sh --workflow <path> --tier L2 --mode dry-run --target <repo>
runtime/run.sh --workflow <path> --tier L2 --mode apply --target <repo>
```

본 디렉토리는 L2-only 검증 헬퍼(예: rollback, conflict diff 생성)가 추가될 자리. v0.10.0-γ 단계에서는 비어 있다.
