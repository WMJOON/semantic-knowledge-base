---
name: skb-ontology
description: |
  Create, edit, query, validate, and reason over SKB ontology graphs whose only
  canonical domain representation is RDF/OWL Turtle. Use for class, property,
  individual, taxonomy, provenance, SHACL, naming, duplicate, and link-integrity work.
metadata:
  version: "1.1.0"
---

# SKB Ontology

SKB ontology data is TTL-only. TBox, RBox, ABox, registry membership, status, and
provenance live in the asserted Turtle graph. Markdown, JSON, and inferred Turtle are
derived projections and must never become competing sources of truth.

Read [references/core.md](references/core.md) before changing a graph or running a
migration. It defines the canonical layout, vocabulary, naming contract, and gates.

## Active workflow

1. Locate `ontology/system/semantic/<domain>/*.ttl`.
2. Edit Turtle directly or use `skb-ontology add` for a managed term/assertion.
3. Run `skb-ontology validate --target REPO [--domain DOMAIN]`.
4. Run `skb-ontology materialize --target REPO --domain DOMAIN --apply` only when an
   inferred projection is needed.

Gate order is fixed: Turtle parse → registry/link completeness → naming and duplicate
checks → SHACL → reasoning. Never reason over a graph that failed an earlier gate.

## Commands

```bash
skb-ontology add --target REPO --domain DOMAIN --kind class \
  --iri https://example.org/kb#Concept --label "개념" \
  --evidence https://example.org/source/1 --apply

skb-ontology add --target REPO --domain DOMAIN --kind object-property \
  --iri https://example.org/kb#relatedTo --label "관련됨" \
  --domain-class https://example.org/kb#Concept \
  --range https://example.org/kb#Concept \
  --evidence https://example.org/source/1 --apply

skb-ontology add --target REPO --domain DOMAIN --kind triple \
  --source https://example.org/kb#left \
  --predicate https://example.org/kb#relatedTo \
  --object https://example.org/kb#right \
  --evidence https://example.org/source/1 --apply

skb-ontology add --target REPO --domain prompt-token --kind concept \
  --iri https://example.org/prompt#emotional --label "감성적" \
  --evidence https://example.org/source/1 --apply

skb-ontology add --target REPO --domain prompt-token --kind triple \
  --source https://example.org/prompt#emotional \
  --predicate http://www.w3.org/2004/02/skos/core#related \
  --object https://example.org/prompt#hanjiCraft \
  --evidence https://example.org/source/1 --apply

skb-ontology list --target REPO [--domain DOMAIN] [--kind class] [--json]
skb-ontology validate --target REPO [--domain DOMAIN]
skb-ontology reason --target REPO --domain DOMAIN [--apply]
skb-ontology materialize --target REPO --domain DOMAIN [--gates-only] [--apply]
```

`compile`, `abox-compile`, JSONL `project`, YAML `rbox/axiom`, and inferred JSONL are
retired from the active contract. Legacy conversion is an explicit, separately reviewed
migration; it is not part of normal ontology authoring.

## Boundaries

- Evidence collection belongs to `skb-evidence`; this skill only records evidence IRIs.
- Human-readable explanation belongs to `skb-explain` and is projected from Turtle.
- Large-impact OWL axioms require the repository's HITL policy even though they are
  authored directly in Turtle.
