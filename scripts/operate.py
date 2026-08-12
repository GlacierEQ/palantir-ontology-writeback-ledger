#!/usr/bin/env python3
"""Execute the real sibling-repo lineage → authorized writeback integration."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.writeback_ledger import (
    ApplyStatus,
    DiffOp,
    ObjectSnapshot,
    OntologyWritebackLedger,
    SignMode,
    WritebackDiff,
)


def load_lineage_module(repo_path: Path):
    file = repo_path / "src" / "lineage.py"
    if not file.is_file():
        raise FileNotFoundError(file)
    spec = importlib.util.spec_from_file_location("glaciereq_action_lineage", file)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load action lineage module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lineage-repo", required=True)
    args = parser.parse_args()

    lineage = load_lineage_module(Path(args.lineage_repo))
    ledger = OntologyWritebackLedger("onto-v3", SignMode.HUMAN_AGENT)
    base = ObjectSnapshot(
        "Aircraft", "A-1", {"status": "ground", "tail": "N1"}, "onto-v3"
    )
    ledger.upsert_base(base)
    diff = WritebackDiff(
        diff_id="cross-repo:1",
        base=base,
        ops=(DiffOp("status", "set", "airborne"),),
        proposed_by="agent:planner",
        authority="change-window:42",
        mode=SignMode.HUMAN_AGENT,
        signatures=("human:ada", "agent:planner"),
        parent_ledger_hash=ledger.tip,
    )

    graph = lineage.LineageGraph()
    steps = [
        lineage.ActionNode(
            "observe:1",
            lineage.ActionKind.ROOT_OBSERVE,
            {"object_type": base.object_type, "object_id": base.object_id, "base_digest": base.content_digest()},
            (),
        ),
        lineage.ActionNode(
            "derive:1",
            lineage.ActionKind.TRANSFORM,
            {"diff_fingerprint": diff.fingerprint(), "operation_count": len(diff.ops)},
            ("observe:1",),
        ),
        lineage.ActionNode(
            "writeback:1",
            lineage.ActionKind.SIDE_EFFECT,
            {
                "writeback": {
                    "object_type": base.object_type,
                    "object_id": base.object_id,
                    "diff_fingerprint": diff.fingerprint(),
                    "proposed_by": diff.proposed_by,
                    "authority": diff.authority,
                    "schema_fingerprint": base.schema_fingerprint,
                    "parent_ledger_hash": diff.parent_ledger_hash,
                    "authorized": True,
                }
            },
            ("derive:1",),
            attestation="review:human+agent",
        ),
    ]
    for node in steps:
        status, reason = graph.commit(node)
        if status is not lineage.CommitStatus.COMMITTED:
            print(json.dumps({"status": "FAIL", "stage": "lineage_commit", "reason": reason}))
            return 2

    proof = graph.export_writeback_proof("writeback:1")
    graph_ok, graph_reason = lineage.verify_proof_bundle(proof)
    if not graph_ok:
        print(json.dumps({"status": "FAIL", "stage": "lineage_self_verify", "reason": graph_reason}))
        return 3

    entry = ledger.apply_authorized(diff, proof)
    current = ledger.get("Aircraft", "A-1")
    output = {
        "status": "PASS" if entry.status is ApplyStatus.APPLIED else "FAIL",
        "lineage_proof_digest": proof["proof_digest"],
        "lineage_fingerprint": proof["lineage_fingerprint"],
        "diff_fingerprint": diff.fingerprint(),
        "ledger_status": entry.status.value,
        "ledger_hash": entry.ledger_hash,
        "resulting_digest": entry.resulting_digest,
        "resulting_status": current.properties.get("status") if current else None,
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if entry.status is ApplyStatus.APPLIED and current and current.properties.get("status") == "airborne" else 4


if __name__ == "__main__":
    raise SystemExit(main())
