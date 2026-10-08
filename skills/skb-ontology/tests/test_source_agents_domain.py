"""참조 도메인 pack(references/domains/source-agents)이 skb-ontology validate(레지스트리·명명·SHACL 게이트)를 통과한다."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
PACK = SKILL / "references" / "domains" / "source-agents"


def _have_deps():
    return subprocess.run([sys.executable, "-c", "import pyshacl, rdflib, owlrl"], capture_output=True).returncode == 0


@unittest.skipUnless(_have_deps(), "pyshacl/rdflib/owlrl 필요")
class DomainPackTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.t = Path(self.td.name)
        d = self.t / "ontology/system/semantic/source-agents"
        d.mkdir(parents=True)
        for f in PACK.glob("*.ttl"):
            shutil.copy(f, d / f.name)

    def tearDown(self):
        self.td.cleanup()

    def run_validate(self):
        env = {**os.environ, "PYTHON": sys.executable}  # 의존성을 확인한 바로 그 인터프리터로 실행한다
        return subprocess.run([str(SKILL / "scripts" / "skb-ontology"), "validate", "--target", str(self.t), "--domain", "source-agents"],
                              capture_output=True, text=True, env=env)

    def test_pack_passes_validate(self):
        r = self.run_validate()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_term_without_provenance_is_caught(self):
        p = self.t / "ontology/system/semantic/source-agents/source-agents.ttl"
        t = p.read_text(encoding="utf-8")
        i = t.index("sa:Person a owl:Class")
        j = t.index("skb:status", i)
        k = t.rindex("prov:hadPrimarySource", i, j)
        e = t.index(";", k) + 1
        p.write_text(t[:k] + t[e:], encoding="utf-8")
        self.assertNotEqual(self.run_validate().returncode, 0)


if __name__ == "__main__":
    unittest.main()
