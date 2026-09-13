"""TTL helpers for MSM workflow SSOT.

MSM workflow execution metadata lives in TTL as the source of truth. YAML is
kept as a migration/edit layer for older workflows.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MSMWF_URI = "https://msm.dev/ontology/workflow#"


def _safe(value: str) -> str:
    return "".join(c if c.isalnum() or c in "-._" else "_" for c in str(value))


def _require_rdflib():
    try:
        from rdflib import BNode, Graph, Literal, Namespace, RDF, URIRef
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError("TTL workflow support requires rdflib") from exc
    return BNode, Graph, Literal, Namespace, RDF, URIRef


def _scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool)) or value is None


def workflow_dict_from_yaml_doc(doc: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    xmsm = doc.get("x_msm") if isinstance(doc.get("x_msm"), dict) else doc
    module = doc.get("module") if isinstance(doc.get("module"), dict) else doc
    gov = xmsm.get("governance") if isinstance(xmsm.get("governance"), dict) else {}
    out: dict[str, Any] = {
        "path": str(path) if path else None,
        "version": module.get("version"),
        "id": module.get("id") or xmsm.get("id") or (path.stem if path else None),
        "category": xmsm.get("category"),
        "kind": xmsm.get("kind"),
        "mode": xmsm.get("mode"),
        "status": xmsm.get("status") or module.get("status"),
        "tool": xmsm.get("tool"),
        "governance": {},
        "pipeline": xmsm.get("pipeline") or [],
    }
    for key in ("hitl_required", "max_retry", "oracle", "oracle_threshold"):
        if key in gov:
            out["governance"][key] = gov[key]
    budget = gov.get("cost_budget")
    if isinstance(budget, dict):
        out["cost_budget"] = {k: v for k, v in budget.items() if _scalar(v)}
    return out


def workflow_dict_to_graph(data: dict[str, Any]):
    BNode, Graph, Literal, Namespace, RDF, URIRef = _require_rdflib()
    g = Graph()
    W = Namespace(MSMWF_URI)
    g.bind("msmwf", W)
    wf_id = data.get("id") or "workflow"
    subj = W["workflow/" + _safe(wf_id)]
    g.add((subj, RDF.type, W.Workflow))
    for key in ("id", "version", "category", "kind", "mode", "status", "tool", "path"):
        value = data.get(key)
        if value is not None:
            g.add((subj, W[key], Literal(value)))
    gov = data.get("governance") or {}
    if gov:
        gb = BNode()
        g.add((subj, W.governance, gb))
        for key, value in gov.items():
            if value is not None:
                g.add((gb, W[key], Literal(value)))
    budget = data.get("cost_budget") or {}
    if budget:
        bb = BNode()
        g.add((subj, W.costBudget, bb))
        for key, value in budget.items():
            if value is not None:
                g.add((bb, W[key], Literal(value)))
    for idx, step in enumerate(data.get("pipeline") or [], 1):
        if not isinstance(step, dict):
            continue
        sb = BNode()
        g.add((subj, W.pipelineStep, sb))
        g.add((sb, W.stepIndex, Literal(idx)))
        for key, value in step.items():
            if _scalar(value) and value is not None:
                g.add((sb, W[key], Literal(value)))
            elif value is not None:
                g.add((sb, W[key + "Json"], Literal(json.dumps(value, ensure_ascii=False, sort_keys=True))))
    return g


def serialize_workflow_ttl(data: dict[str, Any]) -> str:
    return workflow_dict_to_graph(data).serialize(format="turtle")


def parse_workflow_ttl(path: Path) -> dict[str, Any]:
    _, Graph, _, Namespace, RDF, _ = _require_rdflib()
    W = Namespace(MSMWF_URI)
    g = Graph().parse(str(path), format="turtle")
    subjects = list(g.subjects(RDF.type, W.Workflow))
    if not subjects:
        return {"path": str(path), "raw": path.read_text(encoding="utf-8")}
    subj = subjects[0]

    def one(pred: str):
        vals = list(g.objects(subj, W[pred]))
        return vals[0].toPython() if vals else None

    out: dict[str, Any] = {"path": str(path), "raw": path.read_text(encoding="utf-8")}
    for key in ("version", "id", "category", "kind", "mode", "status", "tool"):
        out[key] = one(key)
    gov: dict[str, Any] = {}
    for gb in g.objects(subj, W.governance):
        for key in ("hitl_required", "max_retry", "oracle", "oracle_threshold"):
            vals = list(g.objects(gb, W[key]))
            if vals:
                gov[key] = vals[0].toPython()
    out["governance"] = gov
    budget: dict[str, Any] = {}
    for bb in g.objects(subj, W.costBudget):
        for key in ("tokens", "seconds", "power_wh"):
            vals = list(g.objects(bb, W[key]))
            if vals:
                budget[key] = vals[0].toPython()
    if budget:
        out["cost_budget"] = budget
    steps = []
    for sb in g.objects(subj, W.pipelineStep):
        step: dict[str, Any] = {}
        idx_vals = list(g.objects(sb, W.stepIndex))
        idx = int(idx_vals[0].toPython()) if idx_vals else 0
        for pred, obj in g.predicate_objects(sb):
            key = str(pred).removeprefix(MSMWF_URI)
            if key == "stepIndex":
                continue
            step[key] = obj.toPython()
        steps.append((idx, step))
    out["pipeline"] = [s for _, s in sorted(steps, key=lambda x: x[0])]
    return out


def serialize_index_ttl(workflows: list[dict[str, Any]]) -> str:
    BNode, Graph, Literal, Namespace, RDF, _ = _require_rdflib()
    W = Namespace(MSMWF_URI)
    g = Graph()
    g.bind("msmwf", W)
    idx = W["workflow/index"]
    g.add((idx, RDF.type, W.WorkflowIndex))
    for wf in workflows:
        b = BNode()
        g.add((idx, W.workflowEntry, b))
        for key, value in wf.items():
            if _scalar(value) and value is not None:
                g.add((b, W[key], Literal(value)))
    return g.serialize(format="turtle")


def parse_index_ttl(path: Path) -> list[dict[str, Any]]:
    _, Graph, _, Namespace, RDF, _ = _require_rdflib()
    W = Namespace(MSMWF_URI)
    g = Graph().parse(str(path), format="turtle")
    entries: list[dict[str, Any]] = []
    for idx in g.subjects(RDF.type, W.WorkflowIndex):
        for b in g.objects(idx, W.workflowEntry):
            d: dict[str, Any] = {}
            for pred, obj in g.predicate_objects(b):
                d[str(pred).removeprefix(MSMWF_URI)] = obj.toPython()
            entries.append(d)
    return sorted(entries, key=lambda x: x.get("id", ""))
