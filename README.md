# SKB — Semantic Knowledge Base

SKB is an agent-consumable knowledge-base skill pack. Its ontology domain data is
TTL-only: TBox, RBox, ABox, registry membership, status, and provenance live in
`ontology/system/semantic/**/*.ttl`.

## Canonical boundary

| Data | Canonical format | Location |
|---|---|---|
| Ontology class, property, concept, individual, assertion | Turtle | `ontology/system/semantic/**/*.ttl` |
| Validation shapes | SHACL Turtle | `ontology/system/semantic/**/*.shapes.ttl` |
| Reasoning projection | derived Turtle | `ontology/system/semantic/**/*.inferred.ttl` |
| Evidence catalog and chunks | JSONL and Markdown are allowed | `evidence/seeds.jsonl`, `evidence/md/` |
| Runtime records and events | SQLite, JSONL, Parquet are allowed | `record-archive/` |
| Workflow migration/editing layer | YAML is allowed | `agent-context/workflow/` |
| Human-readable view | derived Markdown | `projection/` |

YAML and JSONL never define ontology terms, relations, instances, axioms, registry
membership, or provenance. Old ontology compilers remain migration history in the private
development repository and are not part of the public TTL-only distribution.

## Skills

- `skb-orchestration`: intent routing, governance, and HITL gates
- `skb-repository-setup`: bootstrap a TTL-only KB layout
- `skb-evidence`: collect, convert and deduplicate source evidence; a source catalog (provenance, retrieval, chunk positions), quote verification, and source-agent registration with human-reviewed identity resolution
- `skb-ontology`: add, list, validate, and report orphans/statistics over Turtle graphs
- `skb-graph-reasoning`: OWL 2 RL reasoning (derived `*.inferred.ttl`), consistency check, SPARQL over the closure
- `skb-semantic-search`: semantic index and search over SKOS concepts and evidence chunks
- `skb-record-archive`: manage operational records outside the ontology
- `skb-harness`: runtime measurement and validation tiers

## Install

```bash
git clone https://github.com/WMJOON/semantic-knowledge-base.git
cd semantic-knowledge-base
python3 -m pip install -r requirements.txt
./install.sh --codex
```

Use `./install.sh`, `--codex`, `--antigravity`, or `--all` to choose an installation
target. The installer creates skill symlinks and does not copy knowledge-base data.

## Quick start

```bash
# Bootstrap a new domain with a valid asserted Turtle graph.
skills/skb-repository-setup/scripts/skb init \
  --target ./my-kb --domain prompt-token --apply --yes

# Add taxonomy concepts.
skills/skb-ontology/scripts/skb-ontology add \
  --target ./my-kb --domain prompt-token --kind concept \
  --iri https://example.org/prompt#emotional --label "감성적" \
  --evidence https://example.org/source/1 --apply

# Validate registry, naming, duplicates, links, provenance, and SHACL.
skills/skb-ontology/scripts/skb-ontology validate \
  --target ./my-kb --domain prompt-token

# Inspect orphans and statistics from the same Turtle source.
skills/skb-ontology/scripts/skb-ontology orphans --target ./my-kb --domain prompt-token
skills/skb-ontology/scripts/skb-ontology stats --target ./my-kb --domain prompt-token

# Check consistency with the OWL 2 RL reasoner.
skills/skb-graph-reasoning/scripts/skb-graph-reasoning check --target ./my-kb
```

See [ontology configuration](docs/guides/ontology-config.md),
[KB structure](docs/kb-directory-structure.md), and the
[agent consumption contract](docs/contracts/agent-consumption-contract.md).

## Validation

```bash
python3 -m pytest -q skills/skb-ontology/tests/test_ttl_only.py
python3 -m pytest -q skills/skb-repository-setup/tests/test_ttl_scaffold.py
python3 -m pytest -q skills/skb-ontology/tests/test_ttl_report.py
python3 -m pytest -q skills/skb-graph-reasoning/tests skills/skb-harness/tests
```

## Security and privacy

Do not commit credentials, private evidence, runtime databases, work-memory records, or
machine-specific absolute paths. Public releases are produced as sanitized snapshots from
the private integration repository and start with clean Git history.

## License

[MIT](LICENSE)
