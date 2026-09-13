# Scaffold Tree

`skb init --apply`가 생성하는 최소 트리. SPEC §5.1 / §5.3.

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
