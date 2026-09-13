import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
MIGRATE = ROOT / "skills" / "skb-orchestration" / "router" / "migrate_workflows_to_ttl.py"
HARNESS_RUNTIME = ROOT / "skills" / "skb-harness" / "runtime"
ROUTER = ROOT / "skills" / "skb-orchestration" / "router"


def _write_workflow(root: Path):
    workflow_root = root / "agent-context" / "workflow"
    workflow = workflow_root / "evidence"
    workflow.mkdir(parents=True)
    wf = workflow / "graphify-etl.yaml"
    wf.write_text(
        yaml.safe_dump(
            {
                "module": {"id": "evidence.graphify.etl", "version": "1.0"},
                "x_msm": {
                    "category": "evidence",
                    "kind": "pipeline",
                    "mode": "dry-run",
                    "status": "draft",
                    "tool": "skb-evidence",
                    "pipeline": [
                        {"step_id": "extract", "tool": "skb-evidence", "action": "graphify_to_skb"}
                    ],
                    "governance": {
                        "hitl_required": False,
                        "max_retry": 1,
                        "oracle": "evidence_seed_readiness",
                        "oracle_threshold": 0.0,
                        "cost_budget": {"tokens": 0, "seconds": 120, "power_wh": None},
                    },
                },
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (workflow_root / "index.yaml").write_text(
        yaml.safe_dump(
            {
                "workflows": [
                    {
                        "id": "graphify-etl",
                        "path": "agent-context/workflow/evidence/graphify-etl.yaml",
                        "category": "evidence",
                        "kind": "pipeline",
                    }
                ]
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return wf


def test_msm_workflow_yaml_migrates_to_ttl_and_runtime_reads(tmp_path, monkeypatch):
    wf = _write_workflow(tmp_path)
    workflow_root = tmp_path / "agent-context" / "workflow"
    subprocess.run([sys.executable, str(MIGRATE), str(workflow_root)], check=True)
    ttl = wf.with_suffix(".abox.ttl")
    assert ttl.exists()
    assert (workflow_root / "index.ttl").exists()

    monkeypatch.syspath_prepend(str(HARNESS_RUNTIME))
    from workflow_parser import parse

    parsed = parse(ttl)
    assert parsed["id"] == "evidence.graphify.etl"
    assert parsed["category"] == "evidence"
    assert parsed["kind"] == "pipeline"
    assert parsed["governance"]["oracle"] == "evidence_seed_readiness"
    assert parsed["pipeline"][0]["step_id"] == "extract"

    subprocess.run([sys.executable, str(MIGRATE), str(workflow_root), "--check"], check=True)


def test_msm_resolver_prefers_index_ttl(tmp_path, monkeypatch):
    _write_workflow(tmp_path)
    subprocess.run([sys.executable, str(MIGRATE), str(tmp_path / "agent-context" / "workflow")], check=True)

    monkeypatch.syspath_prepend(str(ROUTER))
    import resolve_workflow

    resolved = resolve_workflow.resolve(tmp_path, "graphify-etl")
    assert resolved is not None
    assert resolved["path"] == "agent-context/workflow/evidence/graphify-etl.abox.ttl"
    assert resolved["category"] == "evidence"
