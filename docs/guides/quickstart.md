# 빠른 시작

## 설치

```bash
git clone https://github.com/WMJOON/semantic-knowledge-base.git
cd semantic-knowledge-base
pip install -r requirements.txt
./install.sh   # ~/.claude/skills/skb-orchestration 심링크 생성
```

Graphify ETL을 사용하려면:

```bash
pip install graphifyy
```

---

## 새 KB 부트스트랩

```bash
# 미리보기
skills/skb-repository-setup/scripts/skb init \
  --target my-kb --domain ai_agent --dry-run

# 적용
skills/skb-repository-setup/scripts/skb init \
  --target my-kb --domain ai_agent --apply --yes

# 생성 결과
# my-kb/
#   canonical_root_hub.yaml      ← locked SSOT
#   ontology/explain/concept/ai_agent/      ← 클래스·관계 정의 (md + jsonl)
#   ontology/explain/instance/ai_agent/      ← 인스턴스 (md + jsonl)
#   evidence/                    ← 원본·seed
#   workflow/                    ← yaml 정의 워크플로우
#   memory/                      ← task-context + ontology-index
#   harness/                     ← L0~L3 런타임
```

---

## Evidence 수집

### URL / 로컬 MD

```bash
skills/skb-evidence/scripts/skb-evidence collect \
  --target my-kb \
  --source https://arxiv.org/abs/2310.01848 \
  --apply

skills/skb-evidence/scripts/skb-evidence list --target my-kb
```

### Graphify ETL (코드베이스 → concept 노드)

```bash
# 1) 코드베이스 분석
graphify .

# 2) concept 노드만 추출 → MSM JSONL 변환
python skills/skb-evidence/scripts/graphify_to_skb.py \
  graphify-out/graph.json \
  --output-dir my-kb/evidence/graphify/

# 출력
# evidence/graphify/entity_candidates.jsonl   ← concept 노드 (hub_candidate 태그 포함)
# evidence/graphify/relation_candidates.jsonl ← concept 간 관계
```

---

## Ontology 구축

```bash
# class를 canonical Turtle에 직접 추가
skills/skb-ontology/scripts/skb-ontology add \
  --target my-kb --domain ai-agent --kind class \
  --iri https://example.org/kb#ReinforcementLearning \
  --label "Reinforcement Learning" \
  --evidence https://example.org/source/rl --apply

# registry, naming, duplicate, link, SHACL 검증
skills/skb-ontology/scripts/skb-ontology validate --target my-kb --domain ai-agent

# entity 목록
skills/skb-ontology/scripts/skb-ontology list --target my-kb
```

---

## 자연어 라우팅

```bash
# intent → workflow → skill 자동 연결
skills/skb-orchestration/skb-orchestrate run \
  --intent "evidence 수집해줘" \
  --target my-kb --tier L0 --mode dry-run

# 명시적 workflow 호출
skills/skb-orchestration/skb-orchestrate run \
  --workflow workflow/evidence/evidence-collection.yaml \
  --target my-kb --tier L0 --mode dry-run
```

---

## 지원 소스

| 소스 | 방식 |
|------|------|
| URL (웹 페이지·논문) | `skb-evidence collect --source URL` |
| 로컬 MD 파일 | `skb-evidence collect --source ./path` |
| Graphify `graph.json` | `graphify_to_skb.py graph.json` |
