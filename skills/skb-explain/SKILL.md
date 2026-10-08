---
name: skb-explain
description: |
  SKB explain projection layer. record-archive snapshots and ontology semantics
  are rendered into human-readable Markdown/Base generated artifacts.
  Obsidian/Base output remains a supported compatibility target (구 msm-obsidian-projection 은 v1.0.0 에서 폐기).
metadata:
  version: "1.1.0"
---

# skb-explain

## What

`skb-explain` owns the human-readable projection layer.
It reads `record-archive/` snapshots and `ontology/` semantics, then renders generated
Markdown/Base artifacts under `ontology/explain/`.

Obsidian is an output compatibility target, not the skill identity.
The old `skb-explain` name remains a legacy adapter during migration.

## Status — NOT IMPLEMENTED

This skill ships only `SKILL.md`, `harness/run.sh`, and a CLI stub. There is no
`run.py` / `list.py`. The stub used to `exec` itself and forked until the
process limit; it now exits 2 with a pointer instead.

Do not use the retired `skb-ontology project` command. Until a TTL/SPARQL projection
implementation ships, query the asserted graph directly and write derived output outside
the ontology canonical directory.

Everything below describes the intended design, not current behaviour.

## Entry Points

| Entry point | Command |
|-------------|---------|
| CLI — run | `scripts/skb-explain run --target REPO [--domain NAME] [--apply]` — not implemented |
| CLI — list | `scripts/skb-explain list --target REPO` — not implemented |
| Harness | `harness/run.sh --skill skb-explain --tier L0 --mode validate-only --target REPO` |

## Responsibilities

1. Read `record-archive/snapshots/*.parquet` or runtime-derived records.
2. Resolve ontology labels, classes, and provenance into explainable context.
3. Render generated Markdown snapshots for humans.
4. Render Base-compatible indexes when the target vault supports them.
5. Preserve generated-artifact markers and refuse unsafe overwrites.

## Implemented tools

| Tool | Command |
|------|---------|
| Parent-node alignment scan (read-only, Markdown projection) | `python3 scripts/parent_alignment.py --target REPO [--root ontology/explain/concept] [--format json\|markdown] [--accept-hub-suffix]` |

`parent_alignment.py` moved here from the former `skb-maintain`. It checks the human-readable projection
(`{name}__class.md` parent nodes, `belongs_to` frontmatter, bidirectional indexing), which TTL/SHACL does not see.

## Non-Goals

- Record mutation -> `skb-record-archive` or legacy `skb-record-archive`
- Evidence collection -> `skb-evidence`
- Ontology authoring and PROV-O -> `skb-ontology`
- Workflow routing -> `skb-orchestration`
