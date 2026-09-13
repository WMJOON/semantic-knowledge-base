"""MSM↔MSO scaffold 정합 가드.

MSM 의 유일한 MSO 의존: `gen_index.py` 가 `index.yaml` 을 **mso-scaffold-design**
스키마로 생성한다. MSO 의 scaffold 스키마가 바뀌어 MSM 생성물을 깨면 이 테스트가
즉시 실패한다("MSO 업데이트 → MSM 점검"을 사람이 기억할 필요 없게 자동화).

경로 의존: 모노레포 내에서 MSO `sf_node.py` 를 상대경로로 찾는다. 단독 MSM 클론
(MSO 부재)에서는 skip — UUG↔MSO 브리지 테스트와 동일 패턴.
실행: python3 -m pytest tests/ -q   (pyyaml 필요)
"""
import subprocess
import sys
from pathlib import Path

import pytest

# parents: [0]tests [1]skb-repository-setup [2]skills [3]repository
#          [4]11_semantic-knowledge-base [5]integration repository root
_SKILL = Path(__file__).resolve().parents[1]
_GEN_INDEX = _SKILL / "scripts" / "gen_index.py"
_MONOREPO = Path(__file__).resolve().parents[5]
_SF_NODE = (
    _MONOREPO
    / "00_multi-swarm-orchestrator/repository/skills/mso-scaffold-design/scripts/sf_node.py"
)

pytestmark = pytest.mark.skipif(
    not _SF_NODE.exists(),
    reason="MSO mso-scaffold-design/sf_node.py 부재 (단독 MSM 클론) — 정합 가드 skip",
)


def test_gen_index_output_conforms_to_mso_scaffold(tmp_path):
    """MSM gen_index.py 산출 index.yaml 이 현재 MSO sf_node.py validate 를 통과해야 한다.

    실패 = MSO scaffold 스키마가 바뀌어 MSM 생성물이 더는 정합하지 않음 →
    gen_index.py(또는 mso-scaffold-design v2 스키마 참조)를 동기화해야 한다.
    """
    gen = subprocess.run(
        [sys.executable, str(_GEN_INDEX), "--target", str(tmp_path), "--name", "Align Test"],
        capture_output=True, text=True,
    )
    index = tmp_path / "index.yaml"
    assert index.exists(), f"gen_index 가 index.yaml 미생성:\n{gen.stdout}\n{gen.stderr}"

    val = subprocess.run(
        [sys.executable, str(_SF_NODE), "validate", str(index)],
        capture_output=True, text=True,
    )
    assert val.returncode == 0, (
        "MSM gen_index 산출물이 MSO scaffold 스키마 검증 실패 — 스키마 drift.\n"
        f"sf_node 출력:\n{val.stdout}\n{val.stderr}"
    )
