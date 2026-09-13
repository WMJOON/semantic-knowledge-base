#!/usr/bin/env python3
"""capture + collect --capture 테스트 (PRD v0.12.2 §11 AC).

결정적 (네트워크 불필요):
  AC-3  collect without --capture → seed 에 snapshot 필드 없음
  AC-6  비-capture 경로에서 playwright / capture 모듈 미import (lazy)
  AC-4  playwright 부재 시 status="error" + actionable 메시지, 텍스트 수집 계속
  AC-5  snapshot 주입해도 verify 통과 + oracle score 불변 (additive-safe)

옵션 (playwright + chromium + 네트워크 필요 — 없으면 skip):
  AC-1  capture → evidence/captures/<sha>.{pdf,png,html} 3종 생성
  AC-2  collect --capture → 모든 chunk-seed 에 동일 snapshot

실행: python3 tests/test_capture.py
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SK = Path(__file__).resolve().parent.parent
SCRIPTS = SK / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _run(script: Path, *args: str):
    r = subprocess.run([sys.executable, str(script), *args],
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="msm_ev_test_"))
    try:
        (tmp / "src").mkdir(parents=True)
        md = tmp / "src" / "doc.md"
        md.write_text("# Title\n\n" + ("문장 테스트. " * 200), encoding="utf-8")

        import collect as C

        # --- AC-3 + AC-6 ---
        rc = C.main(["--target", str(tmp), "--source", str(md), "--apply"])
        seeds = [json.loads(l) for l in (tmp / "evidence" / "seeds.jsonl").read_text().splitlines() if l.strip()]
        assert rc == 0 and seeds, "collect 실패"
        assert not any("snapshot" in s for s in seeds), "AC-3 FAIL: snapshot 필드 존재"
        assert "playwright" not in sys.modules, "AC-6 FAIL: playwright imported"
        assert "capture" not in sys.modules, "AC-6 FAIL: capture module imported"
        print("[AC-3] no --capture → snapshot 필드 없음 OK")
        print("[AC-6] 비-capture 경로 playwright/capture 미import OK")

        # --- AC-4 ---
        sys.modules["playwright"] = None  # block import
        import capture as CAP
        rec = CAP.capture_to_target("https://example.com/x", tmp)
        err = rec.get("error") or ""
        assert rec["status"] == "error" and "playwright" in err and "pip install" in err, "AC-4 FAIL"
        print("[AC-4] playwright 부재 → status=error + actionable 메시지 OK")
        del sys.modules["playwright"]

        # --- AC-5 ---
        def oracle_score():
            o = SK / "oracle" / "evidence_seed_readiness.py"
            if not o.exists():
                return "n/a"
            _, out = _run(o, "--target", str(tmp))
            m = re.search(r'score"?\s*[:=]\s*([0-9.]+)', out)
            return m.group(1) if m else out.strip()[-40:]

        rc_v0, _ = _run(SCRIPTS / "verify.py", "--target", str(tmp))
        s0 = oracle_score()
        sp = tmp / "evidence" / "seeds.jsonl"
        rows = [json.loads(l) for l in sp.read_text().splitlines() if l.strip()]
        for r in rows:
            r["snapshot"] = {"pdf": "evidence/captures/x.pdf", "png": "evidence/captures/x.png",
                             "html": "evidence/captures/x.html", "captured_at": "2026-06-02T00:00:00Z",
                             "status": "ok"}
        sp.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
        rc_v1, _ = _run(SCRIPTS / "verify.py", "--target", str(tmp))
        s1 = oracle_score()
        assert rc_v0 == 0 and rc_v1 == 0, "AC-5 FAIL: verify"
        assert s0 == s1, f"AC-5 FAIL: oracle score {s0} != {s1}"
        print(f"[AC-5] snapshot 추가 후 verify 통과 + oracle score 불변({s0}) OK")

        # --- AC-1 / AC-2 (optional) ---
        try:
            import playwright  # noqa: F401
            have_pw = True
        except ImportError:
            have_pw = False
        if have_pw:
            kb2 = Path(tempfile.mkdtemp(prefix="msm_ev_cap_"))
            try:
                rc2 = C.main(["--target", str(kb2), "--source", "https://example.com", "--apply", "--capture"])
                cs = [json.loads(l) for l in (kb2 / "evidence" / "seeds.jsonl").read_text().splitlines() if l.strip()]
                snap = cs[0].get("snapshot") if cs else None
                if snap and snap.get("status") == "ok":
                    files_ok = all((kb2 / snap[k]).exists() for k in ("pdf", "png", "html"))
                    same = all(s.get("snapshot") == snap for s in cs)
                    assert files_ok and same, "AC-1/2 FAIL"
                    print("[AC-1/2] 실제 캡처 3종 생성 + 모든 chunk-seed 동일 snapshot OK")
                else:
                    print(f"[AC-1/2] SKIP: 캡처 status={snap and snap.get('status')} "
                          f"(chromium 미설치/네트워크 — error={snap and snap.get('error')})")
            finally:
                shutil.rmtree(kb2, ignore_errors=True)
        else:
            print("[AC-1/2] SKIP: playwright 미설치")

        print("\nDETERMINISTIC CAPTURE ACS (3/4/5/6) PASS")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
