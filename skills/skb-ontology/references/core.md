# SKB ontology TTL-only contract

## Canonical layout

```text
ontology/system/semantic/<domain>/
  <domain>.ttl            asserted TBox, RBox, ABox, registry, provenance
  <domain>.shapes.ttl     SHACL validation graph
  <domain>.inferred.ttl   derived reasoning projection; never hand-edited
```

Additional asserted `*.ttl` files may split a large domain physically. Files ending in
`.shapes.ttl` or `.inferred.ttl` are excluded from the asserted graph loader.

YAML may configure tools outside the domain graph, but it cannot declare ontology terms,
relations, instances, axioms, registry membership, or provenance. JSON/JSONL and Markdown
are projections only.

## Registry vocabulary

Use `skb: <https://semantic-knowledge-base.dev/ontology#>`.

Every domain has at least one `owl:Ontology`. Each user-defined `owl:Class`,
`owl:ObjectProperty`, `owl:DatatypeProperty`, `owl:AnnotationProperty`, and
`owl:NamedIndividual` or `skos:Concept` is linked from that ontology with
`skb:declaresTerm`. A SKOS concept also has exactly one literal `skos:prefLabel`.

Every declared term has exactly one:

- `rdfs:label` per canonical term record;
- `dct:identifier`;
- one or more IRI-valued `prov:hadPrimarySource` links;
- `skb:status` using `draft`, `accepted`, `stable`, or `deprecated`.

Object and datatype properties have exactly one `rdfs:domain` and `rdfs:range`. A direct
object-property assertion must connect two declared terms. Assertions that require their
own provenance are reified as `rdf:Statement` with `prov:hadPrimarySource`.
`skos:related`, hierarchy, and mapping links must connect two declared `skos:Concept`
terms; their endpoints are checked even though SKOS itself is a standard vocabulary.

## Naming and duplicate contract

- Class local names: UpperCamelCase.
- Property local names: lowerCamelCase.
- Individual and SKOS concept local names: lowerCamelCase by default.
- No two declared IRIs may differ only by case.
- `dct:identifier` is unique case-insensitively.
- Labels are compared after Unicode case-folding and whitespace normalization; the same
  language and normalized label cannot identify two declared terms.
- RDF graph set semantics eliminate identical duplicate triples; semantic duplicate gates
  handle different IRIs that would otherwise represent the same term.

## Validation pipeline

```text
parse asserted TTL
  -> registry completeness and declared link targets
  -> naming, identifier, label, and case-fold collision audits
  -> repository SHACL graph
  -> OWL-RL reasoning
  -> derived *.inferred.ttl
```

The validator fails when no asserted Turtle exists. SHACL is not used as a completeness
substitute because missing nodes do not become focus nodes. Reasoning never runs after a
failed gate.

## Migration boundary

The pre-v1.1 JSONL registries and LinkML YAML compiler are legacy inputs. The legacy
compiler scripts themselves have been deleted; `scripts/migrate_legacy_to_ttl.py`
(wired as `skb-ontology migrate-legacy`) is the one-time bridge from a LinkML-style
`classes`/`slots` definition YAML (optionally paired with an `instances` ABox YAML)
into canonical Turtle, with this acceptance boundary:

1. Dry-run by default; convert into asserted Turtle without overwriting the source, and
   never write anything unless `--apply` is given.
2. Require at least one `--evidence` IRI, forced onto `prov:hadPrimarySource` for every
   migrated term and reified assertion — legacy YAML carries no provenance, so none is
   silently fabricated and none is silently omitted.
3. Write the candidate graph into an isolated temp mirror of the target domain and run
   the real `ttl_validate.validate_target` gate (registry/link completeness, naming and
   duplicate audits, domain SHACL) before touching the real target; any failure aborts
   with a report and writes nothing.
4. Obtain repository-required approval before adopting the output.
5. Adopt Turtle as the sole source and archive, rather than continue synchronizing, the
   legacy files.

Never run two compilers against the same asserted Turtle path.
