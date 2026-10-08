"""skb_layout.py 는 graph-reasoning·semantic-search 에 같은 내용으로 복사돼 있어야 한다."""
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[2]


def test_copies_identical():
    a = (SKILLS / "skb-graph-reasoning/scripts/skb_layout.py").read_bytes()
    b = (SKILLS / "skb-semantic-search/scripts/skb_layout.py").read_bytes()
    assert a == b
