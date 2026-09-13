from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from rdflib import RDF, RDFS, Graph, Namespace, URIRef
from rdflib.namespace import OWL, SKOS

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
CLI = SCRIPTS / "skb-ontology"
sys.path.insert(0, str(SCRIPTS))

import ttl_add  # noqa: E402
import ttl_reason  # noqa: E402
import ttl_validate  # noqa: E402
from ttl_common import SKB, canonical_path, load_graph, write_graph  # noqa: E402

EX = Namespace("https://example.org/kb#")
SOURCE = "https://example.org/source/1"


class TTLOnlyOntologyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.domain = "demo"

    def tearDown(self):
        self.temp.cleanup()

    def add(self, *args: str) -> int:
        return ttl_add.main([
            "--target", str(self.root), "--domain", self.domain,
            "--evidence", SOURCE, "--apply", *args,
        ])

    def seed_graph(self):
        self.assertEqual(0, self.add("--kind", "class", "--iri", str(EX.Agent), "--label", "에이전트"))
        self.assertEqual(0, self.add("--kind", "class", "--iri", str(EX.Organization), "--label", "조직"))
        self.assertEqual(0, self.add(
            "--kind", "object-property", "--iri", str(EX.memberOf), "--label", "소속",
            "--domain-class", str(EX.Agent), "--range", str(EX.Organization),
        ))
        self.assertEqual(0, self.add(
            "--kind", "individual", "--iri", str(EX.alice), "--label", "앨리스", "--type", str(EX.Agent),
        ))
        self.assertEqual(0, self.add(
            "--kind", "individual", "--iri", str(EX.acme), "--label", "애크미", "--type", str(EX.Organization),
        ))

    def test_direct_ttl_add_link_and_validation(self):
        self.seed_graph()
        self.assertEqual(0, self.add(
            "--kind", "triple", "--source", str(EX.alice),
            "--predicate", str(EX.memberOf), "--object", str(EX.acme),
        ))
        paths, graph, failures = ttl_validate.validate_target(self.root, self.domain)
        self.assertEqual([], failures)
        self.assertEqual(1, len(paths))
        self.assertIn((EX.alice, EX.memberOf, EX.acme), graph)
        self.assertFalse(list(self.root.rglob("*.yaml")))
        self.assertFalse(list(self.root.rglob("*.jsonl")))

    def test_duplicate_normalized_label_is_blocked(self):
        self.assertEqual(0, self.add("--kind", "class", "--iri", str(EX.Agent), "--label", "에이전트"))
        self.assertEqual(1, self.add("--kind", "class", "--iri", str(EX.Worker), "--label", "  에이전트  "))

    def test_case_folded_iri_collision_is_blocked(self):
        self.assertEqual(0, self.add("--kind", "class", "--iri", str(EX.Agent), "--label", "에이전트"))
        path = canonical_path(self.root, self.domain)
        graph = load_graph([path])
        ontology = next(graph.subjects(RDF.type, OWL.Ontology))
        graph.add((ontology, SKB.declaresTerm, EX.agent))
        graph.add((EX.agent, RDF.type, OWL.Class))
        graph.add((EX.agent, RDFS.label, URIRef("https://example.org/not-a-literal")))
        graph.add((EX.agent, URIRef("http://purl.org/dc/terms/identifier"), URIRef("https://example.org/not-a-literal")))
        graph.add((EX.agent, URIRef("http://www.w3.org/ns/prov#hadPrimarySource"), URIRef(SOURCE)))
        write_graph(path, graph)
        _, _, failures = ttl_validate.validate_target(self.root, self.domain)
        self.assertTrue(any("case-folded IRI collision" in failure for failure in failures), failures)

    def test_dangling_object_link_is_blocked(self):
        self.seed_graph()
        path = canonical_path(self.root, self.domain)
        graph = load_graph([path])
        graph.add((EX.alice, EX.memberOf, EX.missingOrganization))
        write_graph(path, graph)
        _, _, failures = ttl_validate.validate_target(self.root, self.domain)
        self.assertTrue(any("dangling object-property target" in failure for failure in failures), failures)

    def test_undeclared_custom_predicate_is_blocked(self):
        self.seed_graph()
        path = canonical_path(self.root, self.domain)
        graph = load_graph([path])
        graph.add((EX.alice, EX.unknownLink, EX.acme))
        write_graph(path, graph)
        _, _, failures = ttl_validate.validate_target(self.root, self.domain)
        self.assertTrue(any("custom predicate is not a declared" in failure for failure in failures), failures)

    def test_skos_related_connects_declared_taxonomy_concepts(self):
        self.assertEqual(0, self.add(
            "--kind", "concept", "--iri", str(EX.emotional), "--label", "감성적",
        ))
        self.assertEqual(0, self.add(
            "--kind", "concept", "--iri", str(EX.hanjiCraft), "--label", "한지 공예",
        ))
        self.assertEqual(0, self.add(
            "--kind", "triple", "--source", str(EX.emotional),
            "--predicate", str(SKOS.related), "--object", str(EX.hanjiCraft),
        ))
        _, graph, failures = ttl_validate.validate_target(self.root, self.domain)
        self.assertEqual([], failures)
        self.assertIn((EX.emotional, SKOS.related, EX.hanjiCraft), graph)

    def test_reasoning_output_is_turtle(self):
        self.assertEqual(0, self.add("--kind", "class", "--iri", str(EX.Agent), "--label", "에이전트"))
        self.assertEqual(0, self.add("--kind", "class", "--iri", str(EX.Person), "--label", "사람"))
        self.assertEqual(0, self.add(
            "--kind", "individual", "--iri", str(EX.alice), "--label", "앨리스", "--type", str(EX.Person),
        ))
        path = canonical_path(self.root, self.domain)
        graph = load_graph([path])
        graph.add((EX.Person, RDFS.subClassOf, EX.Agent))
        write_graph(path, graph)
        inferred = ttl_reason.reason(self.root, self.domain)
        self.assertIn((EX.alice, RDF.type, EX.Agent), inferred)

    def test_legacy_compiler_is_not_an_active_cli_path(self):
        result = subprocess.run(
            [str(CLI), "compile", "--target", str(self.root)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("retired", result.stderr)

    def test_explicit_shacl_cli_reads_turtle_only(self):
        fixture = Path(__file__).parent / "fixtures" / "ttl_demo"
        result = subprocess.run(
            [str(CLI), "shapes-validate", "--target", str(fixture), "--domain", "demo"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("PASS demo", result.stdout)


if __name__ == "__main__":
    unittest.main()
