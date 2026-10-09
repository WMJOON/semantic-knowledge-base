<!-- msm:generated:file skill="skb-repository-setup" version="1.0.0" -->

# {{KB_NAME}} — Work Memory

작업 기억(work-memory)은 auditlog/worklog(자동)와 track-record/insight-record(수동 큐레이션)로 나뉜다.

- `auditlog/` — PostToolUse 자동 로깅
- `worklog/` — workflow node 실행 기록
- `track-record/` — issue-note · agent-decision · alternatives-record · user-decision · trouble-shooting
- `insight-record/` — episode · pattern · principle

CLI: `mso-work-memory` 스킬의 `wm_node.py` (new/validate/search/graph/relate), `wm_context.py` (context pack 검색), `wm_release.py` (release derived view).
