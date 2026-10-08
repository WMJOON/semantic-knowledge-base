from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))
import dispatch as D  # noqa: E402


def test_sibling_skill_is_found_without_any_env(monkeypatch):
    for k in list(__import__("os").environ):
        if k.startswith(("SKB_SKILL_", "MSM_SKILL_")):
            monkeypatch.delenv(k)
    assert D._locate_skill("skb-ontology").name == "skb-ontology"


def test_skb_env_override_beats_sibling_and_msm_alias_still_works(monkeypatch, tmp_path):
    home = tmp_path / "custom"
    home.mkdir()
    monkeypatch.setenv("SKB_SKILL_SKB_ONTOLOGY_HOME", str(home))
    assert D._locate_skill("skb-ontology") == home.resolve()
    monkeypatch.delenv("SKB_SKILL_SKB_ONTOLOGY_HOME")
    monkeypatch.setenv("MSM_SKILL_SKB_ONTOLOGY_HOME", str(home))
    assert D._locate_skill("skb-ontology") == home.resolve()


def test_provider_skill_roots_are_searched_when_no_sibling(monkeypatch, tmp_path):
    root = tmp_path / ".claude" / "skills" / "only-in-home"
    root.mkdir(parents=True)
    monkeypatch.setattr(D.Path, "home", classmethod(lambda cls: tmp_path))
    assert D._locate_skill("only-in-home") == root.resolve()


def test_unknown_skill_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(D.Path, "home", classmethod(lambda cls: tmp_path))
    assert D._locate_skill("no-such-skill-xyz") is None
