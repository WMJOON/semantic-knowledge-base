# Skill Link Install Targets (SPEC §7)

`--with-skill-links`로만 활성화. 기본 `skb init`은 $HOME을 건드리지 않는다 (AC-RS-6).

| 대상 | 링크 |
|------|------|
| modules | `~/.claude/skills -> <repo>/repository/.skill-modules` |
| Claude orchestration | `~/.claude/skills/skb-orchestration -> <repo>/repository/skills/skb-orchestration` |
| Codex orchestration | `~/.codex/skills/skb-orchestration -> <repo>/repository/skills/skb-orchestration` |

## v0.10.0 pack_config 모드

| mode | 설명 |
|------|------|
| compatibility | v0.2.0 required_skills 누락을 warn으로 처리 |
| v1-strict | v0.10.0 8개 스킬(`skb-repository-setup`, `skb-evidence`, `skb-ontology`, `skb-maintain`, `skb-graph-reasoning`, `skb-semantic-search`, `skb-harness`, `skb-orchestration`) 모두 존재해야 함 |

본 v0.10.0-β 단계는 compatibility 모드만 검증한다. v1-strict는 `skb-orchestration-v0.10.0-SPEC` 확정 후 활성화 (RS-OI-2).
