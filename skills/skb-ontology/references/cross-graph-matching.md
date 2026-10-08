# Cross-graph matching (research note, not adopted)

> Status: documented only. No skb-ontology gate, script, or test implements this.
> Source PRD: `planning/skb-ontology_v1.2.0/skb-ontology_v1.2.0-cross-graph-matching-and-oxigraph-research-PRD.md`
> Origin: MyCopilot repository, Biz-Gate commerce API survey, 2026-09-16/17.

## Pattern

Keep "what exists" (an evidence graph) and "what is required" (a requirement graph) as
two separate TTL ontologies. The matching rule between them is stored as data in the
requirement graph, not as Python logic outside any graph. A matching run reads the rules
via SPARQL, assembles a `CONTAINS`/`FILTER` query per requirement attribute, executes it
against the evidence graph, and materializes results back as triples
(`coveredBy`-style links). CSV/MD views of the match are derived projections, never SoT.

This differs from keyword-list-in-Python matching in one respect: because the rule lives
in the graph, SHACL can validate it and SPARQL can execute it. A Python `in` check reaches
neither.

## Reference vocabulary

| Term | Kind | Meaning |
|---|---|---|
| `CanonicalEntity` / `CanonicalAttribute` | Class | required entity / required attribute |
| `belongsToEntity`, `attributeLabel`, `direction` (inbound/outbound/both) | structure | |
| `matchKeyword` (1..n) | rule | any hit in the combined text → candidate (OR) |
| `groupFilterTerm` (0..n) | rule | combined entity name + domain must contain this to qualify (scopes the match) |
| `excludeTerm` (0..n) | rule | a hit removes the candidate (blocks homonym false positives) |
| `requiresEndpointContext` (bool) | rule | include endpoint description text in the group-filter check |
| `coveredBy` | result | `CanonicalAttribute` → matched evidence attribute IRI |

SHACL constraints used in the reference implementation: `matchKeyword minCount 1`,
`direction sh:in (...)`, `belongsToEntity sh:class`.

## Pitfalls (verified in production use, 28 platforms / 86,694 triples / 3,218 matches)

1. **Shared entity comments leak into matching.** If the combined match text includes an
   entity-level `rdfs:comment`, one keyword in that shared description matches every
   attribute of the entity. Correct for a single-purpose entity, a false positive for a
   general-purpose one (e.g. one word in a `Customer` comment pulled in 16 unrelated
   fields). `excludeTerm` only partially compensates — it also removes genuine matches in
   the same entity.
2. **Single GraphQL endpoints defeat path-based grouping.** Grouping entities by
   endpoint path collapses every mutation into one bucket when an API exposes a single
   `/graphql` route. Treat such endpoints as non-decomposable and exclude them rather
   than force a group.
3. **Short keywords collide as substrings.** `eta` ⊂ `detail`/`retail`, `point` ⊂
   `endpoint`, `address` ⊂ `email_address`/"이메일 주소". Keep 3–5 character keywords
   (English or Korean) as compound terms only, never bare.
4. **rdflib `GROUP_CONCAT` with multiple independent `OPTIONAL`s errors on unbound
   variables.** Aggregate each multi-valued attribute in its own query instead of one
   combined query.
5. **Unverified comments drift from data.** A comment can assert a field name that does
   not exist in the source. Treat comments as claims to check against the source, not as
   exempt from review.
6. **The same target collected twice, differently.** A hand-authored TTL and a
   machine-converted catalog can describe the same API under different field names with
   no single source of truth between them, silently depressing match rates. Pick one SoT
   per target before matching.

## Deferred: pyoxigraph query backend

The same PRD measured pyoxigraph 0.5.11 against rdflib 7 on the matching workload above
(70 `CONTAINS`/`FILTER` queries over 86,694 triples): 289.9s (rdflib) vs. 5.0s
(pyoxigraph, in-memory `Store()`, no disk persistence needed) — about 56x, because rdflib
evaluates `CONTAINS`/`FILTER` with a linear scan per query.

This does not apply to skb-ontology today: none of the active TTL-only scripts
(`ttl_list.py`, `ttl_validate.py`, `ttl_report.py`) issue SPARQL
queries — they walk the rdflib graph directly (`.objects()`/`.value()`/`.triples()`).
There is currently no SPARQL query path for a pyoxigraph backend to accelerate. Revisit
this only if/when a SPARQL-based query path (e.g. a future `match` subcommand
implementing the pattern above) is adopted; see the PRD §3.2 for the rdflib→pyoxigraph
API migration checklist at that point.

## Not resolved by this note

- Whether a semantic verification gate (local LLM first pass, human confirms) belongs in
  the skb gate order. Small local models hallucinate specific values, so any such gate
  would need "model flags, human decides" as a hard constraint.
- Keyword-based matching is inherently approximate; if a controlled vocabulary
  (`canonicalField`-style) is normalized later, exact matching could replace `CONTAINS`.
- Impact on existing skb-ontology tests is unassessed, because no code path exists yet to
  test.
