import sys
import unittest
from pathlib import Path
from rdflib import Graph, Namespace, Literal, RDF, RDFS
from rdflib.namespace import OWL, SKOS, PROV, DCTERMS
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ttl_validate import audit
from ttl_common import SKB
EX = Namespace('https://example.org/concept#')

class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.g = Graph()
        self.g.add((EX.registry, RDF.type, OWL.Ontology))
        self.g.add((EX.scheme, RDF.type, SKOS.ConceptScheme))

    def term(self, name, label='agent'):
        t=EX[name]
        for p,o in [(RDF.type, SKOS.Concept), (RDFS.label,Literal(label,lang='en')),
                    (SKOS.prefLabel,Literal(label,lang='en')),
                    (DCTERMS.identifier,Literal('concept:'+name)),(SKB.status,Literal('draft')),
                    (SKOS.scopeNote,Literal('Meaning in '+name)),(SKOS.inScheme,EX.scheme),
                    (PROV.wasDerivedFrom,EX.source)]: self.g.add((t,p,o))
        self.g.add((EX.registry,SKB.declaresTerm,t))
        return t

    def test_homonyms_and_multilingual_labels(self):
        a=self.term('technology-agent'); self.term('business-agent')
        self.g.add((a,SKOS.prefLabel,Literal('에이전트',lang='ko')))
        self.assertEqual([],audit(self.g))

    def test_same_language_preferred_label_rejected(self):
        a=self.term('technology-agent')
        self.g.add((a,SKOS.prefLabel,Literal('another agent',lang='en')))
        self.assertTrue(any('[C8]' in f for f in audit(self.g)))

    def test_identifier_collision_rejected(self):
        a=self.term('technology-agent'); b=self.term('business-agent')
        self.g.set((b,DCTERMS.identifier,Literal('concept:technology-agent')))
        self.assertTrue(any('[D2]' in f for f in audit(self.g)))

    def test_new_camelcase_rejected(self):
        self.term('technologyAgent')
        self.assertTrue(any('[N4]' in f for f in audit(self.g)))

    def test_cycle_rejected_and_direction_preserved(self):
        a=self.term('technology-ai-agent'); b=self.term('technology-software-agent')
        self.g.add((a,SKOS.broader,b))
        self.assertEqual([],audit(self.g))
        self.g.add((b,SKOS.broader,a))
        self.assertTrue(any('[H1]' in f for f in audit(self.g)))

    def test_version_record_source(self):
        a=self.term('technology-agent')
        self.g.remove((a,PROV.wasDerivedFrom,None))
        self.g.add((a,DCTERMS.provenance,EX.record))
        self.g.add((EX.record,PROV.wasDerivedFrom,EX.source))
        self.assertEqual([],audit(self.g))
        self.g.remove((EX.record,PROV.wasDerivedFrom,None))
        self.assertTrue(any('[C5]' in f for f in audit(self.g)))

    def test_owl_class_not_a_concept(self):
        a=self.term('technology-agent')
        self.g.add((a,RDF.type,OWL.Class))
        self.assertTrue(any('[C6]' in f for f in audit(self.g)))

if __name__ == '__main__': unittest.main()
