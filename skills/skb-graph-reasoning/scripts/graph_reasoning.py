#!/usr/bin/env python3
"""skb-graph-reasoning — OWL 2 RL 추론기 CLI.

  graph_reasoning.py reason  --target KB --domain D [--apply] [--print] [--keep-trivial] [--rdfs] [--no-validate] [--allow-inconsistent]
  graph_reasoning.py check   --target KB [--domain D] [--rdfs] [--json] [--strict-datatypes]   비일관성 점검 (있으면 종료 코드 1)
  graph_reasoning.py stats   --target KB --domain D [--rdfs] [--json]          무엇이 얼마나 파생되는가
  graph_reasoning.py status  --target KB --domain D [--json]                   파생 TTL 신선도 (fresh 아니면 종료 코드 1)
  graph_reasoning.py query   --target KB [--domain D] (--sparql Q | --file F) [--no-closure] [--json] [--limit N]

정본 TTL 은 수정하지 않는다. 쓰는 것은 --apply 일 때의 <domain>/<name>.inferred.ttl 뿐이다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reasoner as R  # noqa: E402


def _validate(target: Path, domain):
    """형제 스킬 skb-ontology 가 있으면 추론 전에 asserted TTL 을 검증한다. 없거나 못 쓰면 (None, 사유)."""
    here = Path(__file__).resolve()
    home = os.environ.get("SKB_SKILL_SKB_ONTOLOGY_HOME")
    scripts = (Path(home) if home else here.parents[2] / "skb-ontology") / "scripts"
    if not (scripts / "ttl_validate.py").exists():
        return None, "skb-ontology 를 찾지 못해 검증을 건너뛴다"
    sys.path.insert(0, str(scripts))
    try:
        from ttl_validate import validate_target  # type: ignore
    except Exception as exc:  # pyshacl 등 의존성 부재
        return None, "skb-ontology 검증을 불러오지 못해 건너뛴다 (%s)" % type(exc).__name__
    return validate_target(target, domain)[2], None


def _load(a):
    files = R.asserted_files(a.target, a.domain)
    if not files:
        sys.exit("asserted TTL 이 없다: %s" % (R.semantic_root(a.target) / (a.domain or "")))
    return files, R.load_graph(files)


def cmd_reason(a) -> int:
    if not a.domain:
        sys.exit("--domain 이 필요하다 (파생 TTL 은 도메인마다 하나)")
    if not a.no_validate:
        failures, why = _validate(a.target, a.domain)
        if why:
            print("NOTE:", why, file=sys.stderr)
        elif failures:
            for f in failures:
                print("FAIL", f, file=sys.stderr)
            print("asserted TTL 검증 실패 %d건 — 추론하지 않는다 (--no-validate 로 건너뛸 수 있음)" % len(failures), file=sys.stderr)
            return 1
    files, g = _load(a)
    inferred, errors, artifacts = R.infer(g, keep_trivial=a.keep_trivial, rdfs=a.rdfs)
    print("asserted=%d inferred=%d inconsistencies=%d xsd_artifacts=%d" % (len(g), len(inferred), len(errors), len(artifacts)))
    print("by kind:", json.dumps(R.categorize(inferred), ensure_ascii=False))
    for e in errors:
        print("INCONSISTENT:", e, file=sys.stderr)
    if errors and not a.allow_inconsistent:
        print("비일관성이 있어 파생 TTL 을 쓰지 않는다 (--allow-inconsistent 로 강제)", file=sys.stderr)
        return 3
    if a.print:
        print(inferred.serialize(format="turtle"))
    if a.apply:
        path = R.write_inferred(a.target, a.domain, inferred, R.source_hash(a.target, files), files, rdfs=a.rdfs)
        print(path)
    return 0


def cmd_check(a) -> int:
    files, g = _load(a)
    _, errors, artifacts = R.closure(g, rdfs=a.rdfs)
    if a.strict_datatypes:
        errors = errors + artifacts
    if a.json:
        print(json.dumps({"files": len(files), "triples": len(g), "inconsistencies": errors, "xsd_artifacts": len(artifacts)}, ensure_ascii=False, indent=1))
    else:
        print("files=%d triples=%d inconsistencies=%d xsd_artifacts=%d" % (len(files), len(g), len(errors), len(artifacts)))
        for e in errors:
            print(" ", e)
        if artifacts and not a.strict_datatypes:
            print("  (xsd_artifacts: 같은 어휘형이 문자열과 숫자로 함께 쓰인 데이터형 표기 문제, 논리 모순 아님 — --strict-datatypes 로 포함)")
    return 1 if errors else 0


def cmd_stats(a) -> int:
    files, g = _load(a)
    inferred, errors, artifacts = R.infer(g, rdfs=a.rdfs)
    out = {"files": len(files), "asserted": len(g), "inferred": len(inferred), "by_kind": R.categorize(inferred), "inconsistencies": len(errors), "xsd_artifacts": len(artifacts)}
    print(json.dumps(out, ensure_ascii=False, indent=1) if a.json else "\n".join("%s: %s" % kv for kv in out.items()))
    return 0


def cmd_status(a) -> int:
    if not a.domain:
        sys.exit("--domain 이 필요하다")
    st = R.status(a.target, a.domain)
    print(json.dumps(st, ensure_ascii=False, indent=1) if a.json else "%s  %s%s" % (st["state"], st["domain"], ("  (%s)" % st["reason"]) if "reason" in st else ""))
    return 0 if st["state"] == "fresh" else 1


def cmd_query(a) -> int:
    sparql = Path(a.file).read_text(encoding="utf-8") if a.file else a.sparql
    if not sparql:
        sys.exit("--sparql 또는 --file 이 필요하다")
    _, g = _load(a)
    res = R.query(g, sparql, with_closure=not a.no_closure, rdfs=a.rdfs)
    if res.type == "ASK":
        print(json.dumps({"ask": bool(res.askAnswer)}))
        return 0 if res.askAnswer else 1
    vars_ = [str(v) for v in res.vars]
    rows = [{v: (str(row[v]) if row[v] is not None else None) for v in vars_} for row in res]
    if a.limit:
        rows = rows[: a.limit]
    if a.json:
        print(json.dumps({"vars": vars_, "rows": rows}, ensure_ascii=False, indent=1))
    else:
        print("\t".join(vars_))
        for r in rows:
            print("\t".join("" if r[v] is None else r[v] for v in vars_))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, domain_required=False):
        p.add_argument("--target", required=True, type=Path, help="KB 루트")
        p.add_argument("--domain", required=domain_required, help="semantic 도메인 경로 (예: academic/finance)")
        p.add_argument("--rdfs", action="store_true", help="RDFS 규칙도 함께 적용")

    p = sub.add_parser("reason"); common(p)
    p.add_argument("--apply", action="store_true"); p.add_argument("--print", action="store_true")
    p.add_argument("--keep-trivial", action="store_true", help="sameAs 반사 등 의미 없는 파생도 남긴다")
    p.add_argument("--no-validate", action="store_true"); p.add_argument("--allow-inconsistent", action="store_true")
    p.set_defaults(fn=cmd_reason)
    p = sub.add_parser("check"); common(p); p.add_argument("--json", action="store_true"); p.add_argument("--strict-datatypes", action="store_true", help="XSD 값 공간 아티팩트도 비일관성으로 센다"); p.set_defaults(fn=cmd_check)
    p = sub.add_parser("stats"); common(p); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_stats)
    p = sub.add_parser("status"); common(p); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_status)
    p = sub.add_parser("query"); common(p)
    p.add_argument("--sparql"); p.add_argument("--file"); p.add_argument("--no-closure", action="store_true")
    p.add_argument("--json", action="store_true"); p.add_argument("--limit", type=int)
    p.set_defaults(fn=cmd_query)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
