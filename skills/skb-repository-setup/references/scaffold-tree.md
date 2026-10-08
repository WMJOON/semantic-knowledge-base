# Scaffold Tree

`skb init --apply`가 생성하는 최소 트리. SPEC §5.1 / §5.3.

기본 배치는 `b1`이다. 아래 트리는 `legacy`(옛 배치)이고, `b1`은 달라지는 부분이 다음과 같다. `canonical_root_hub.yaml`의 `layout:`이 이 경로를 선언한다.

```text
ontology/semantic/{domain}/{domain}.ttl       # legacy: ontology/system/semantic/
ontology/system/{kinetic,dynamic}/{cluster}.ttl
evidence/artifact/raw/                         # legacy: evidence/raw/
evidence/chunk/                                # legacy: evidence/md/
evidence/catalog/seeds.jsonl                   # legacy: evidence/seeds.jsonl
evidence/{captures,graphify}/
agent-context/index/artifacts.abox.ttl         # artifact 레지스트리
agent-context/workflow/workflow-{evidence-collection,ontology-construction,validation,search-reason}.abox.ttl
.gitignore                                     # 원문·파생물·실행 기록 제외 (이미 있으면 유지)
```

b1은 YAML 워크플로우와 `workflow/index.yaml`을 만들지 않는다.

```text
<repo-root>/
├── ontology/
│   ├── system/
│   │   ├── semantic/{domain}/{domain}.ttl
│   │   ├── kinetic/{cluster}.ttl
│   │   └── dynamic/{cluster}.ttl
├── projection/
│   └── wikigraph/
│       ├── class/{domain}/{domain}__class.md
│       └── instance/{domain}/
├── evidence/
│   ├── md/
│   ├── raw/
│   ├── captures/
│   ├── graphify/
│   └── seeds.jsonl
├── record-archive/
│   ├── registry/instance-ids.jsonl
│   ├── runtime/
│   ├── events/
│   ├── derived/
│   ├── snapshots/
│   └── schema/
├── planning/{research,ontology}/
├── report/paper/
├── docs/{index.md,guideline/}
├── agent-context/
│   ├── index/index.yaml
│   └── workflow/
│       ├── index.yaml
│       ├── evidence/evidence-collection.yaml
│       ├── ontology/ontology-construction.yaml
│       ├── maintain/validation.yaml
│       └── explorer/search-reason.yaml
├── agent-context/work-memory/
│   ├── auditlog/
│   ├── worklog/
│   ├── track-record/
│   ├── insight-record/
│   └── index.md
├── harness/
│   ├── run.sh
│   ├── tiers/{L0_static,L1_fixture,L2_integration,L3_eval}/
│   ├── fixtures/
│   └── trajectory/
├── .claude/{skills,hooks}/
├── .codex/{skills,hooks}/         # --targets에 codex 포함 시
└── canonical_root_hub.yaml
```

domain 없이 init하면 `domains: []`인 빈 hub만 생성된다.
