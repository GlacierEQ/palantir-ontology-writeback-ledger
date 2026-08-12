from __future__ import annotations

import copy
import unittest

from src.lineage_proof import digest
from src.writeback_ledger import (
    ApplyStatus,
    DiffOp,
    ObjectSnapshot,
    OntologyWritebackLedger,
    SignMode,
    WritebackDiff,
)


def _node(action_id, kind, payload, parents, attestation=None):
    body = {
        "id": action_id,
        "kind": kind,
        "payload": payload,
        "parents": list(parents),
        "attestation": attestation,
    }
    return {**body, "fingerprint": digest(body)}


def proof_for(diff: WritebackDiff):
    nodes = [
        _node(
            "observe:1",
            "ROOT_OBSERVE",
            {"object_type": diff.base.object_type, "object_id": diff.base.object_id},
            [],
        ),
        _node(
            "derive:1",
            "TRANSFORM",
            {"proposal": [(op.path, op.op, op.value) for op in diff.ops]},
            ["observe:1"],
        ),
        _node(
            "writeback:1",
            "SIDE_EFFECT",
            {
                "writeback": {
                    "object_type": diff.base.object_type,
                    "object_id": diff.base.object_id,
                    "diff_fingerprint": diff.fingerprint(),
                    "proposed_by": diff.proposed_by,
                    "authority": diff.authority,
                    "schema_fingerprint": diff.base.schema_fingerprint,
                    "parent_ledger_hash": diff.parent_ledger_hash,
                    "authorized": True,
                }
            },
            ["derive:1"],
            "review:human+agent",
        ),
    ]
    lineage = digest(
        {
            "tip": "writeback:1",
            "nodes": [
                {"id": node["id"], "fingerprint": node["fingerprint"]}
                for node in sorted(nodes, key=lambda item: item["id"])
            ],
        }
    )
    proof = {
        "schema": "glaciereq.action-lineage-proof.v1",
        "tip": "writeback:1",
        "lineage_fingerprint": lineage,
        "nodes": nodes,
    }
    proof["proof_digest"] = digest(proof)
    return proof


class AuthorizedWritebackTests(unittest.TestCase):
    def setUp(self):
        self.schema = "onto-v3"
        self.ledger = OntologyWritebackLedger(self.schema, SignMode.HUMAN_AGENT)
        self.base = ObjectSnapshot(
            "Aircraft", "A-1", {"status": "ground", "tail": "N1"}, self.schema
        )
        self.ledger.upsert_base(self.base)

    def diff(self):
        return WritebackDiff(
            diff_id="authorized:1",
            base=self.base,
            ops=(DiffOp("status", "set", "airborne"),),
            proposed_by="agent:planner",
            authority="change-window:42",
            mode=SignMode.HUMAN_AGENT,
            signatures=("human:ada", "agent:planner"),
            parent_ledger_hash=self.ledger.tip,
        )

    def test_valid_lineage_proof_allows_normal_transaction(self):
        diff = self.diff()
        entry = self.ledger.apply_authorized(diff, proof_for(diff))
        self.assertIs(entry.status, ApplyStatus.APPLIED)
        current = self.ledger.get("Aircraft", "A-1")
        assert current is not None
        self.assertEqual(current.properties["status"], "airborne")

    def test_bad_proof_does_not_mutate_reserve_diff_or_advance_tip(self):
        diff = self.diff()
        proof = proof_for(diff)
        bad = copy.deepcopy(proof)
        bad["nodes"][-1]["payload"]["writeback"]["authority"] = "attacker"
        # Recompute the outer digest only. Inner node fingerprint remains bound to the original claim.
        body = dict(bad)
        body.pop("proof_digest")
        bad["proof_digest"] = digest(body)

        tip_before = self.ledger.tip
        entry = self.ledger.apply_authorized(diff, bad)
        self.assertIs(entry.status, ApplyStatus.REFUSED)
        self.assertTrue(entry.refuse_reason and entry.refuse_reason.startswith("LINEAGE_"))
        self.assertEqual(self.ledger.tip, tip_before)
        self.assertEqual(self.ledger.get("Aircraft", "A-1"), self.base)

        corrected = self.ledger.apply_authorized(diff, proof)
        self.assertIs(corrected.status, ApplyStatus.APPLIED)

    def test_proof_for_different_diff_is_refused(self):
        original = self.diff()
        proof = proof_for(original)
        other = WritebackDiff(
            diff_id="authorized:2",
            base=self.base,
            ops=(DiffOp("tail", "set", "N2"),),
            proposed_by=original.proposed_by,
            authority=original.authority,
            mode=original.mode,
            signatures=original.signatures,
            parent_ledger_hash=original.parent_ledger_hash,
        )
        entry = self.ledger.apply_authorized(other, proof)
        self.assertEqual(
            entry.refuse_reason,
            "LINEAGE_WRITEBACK_BINDING_MISMATCH:diff_fingerprint",
        )

    def test_proof_cannot_authorize_another_object(self):
        diff = self.diff()
        proof = proof_for(diff)
        other_base = ObjectSnapshot(
            "Aircraft", "A-2", {"status": "ground"}, self.schema
        )
        self.ledger.upsert_base(other_base)
        other = WritebackDiff(
            diff_id="authorized:other-object",
            base=other_base,
            ops=(DiffOp("status", "set", "airborne"),),
            proposed_by=diff.proposed_by,
            authority=diff.authority,
            mode=diff.mode,
            signatures=diff.signatures,
            parent_ledger_hash=diff.parent_ledger_hash,
        )
        entry = self.ledger.apply_authorized(other, proof)
        self.assertEqual(
            entry.refuse_reason,
            "LINEAGE_WRITEBACK_BINDING_MISMATCH:object_id",
        )

    def test_unreachable_extra_node_refuses(self):
        diff = self.diff()
        proof = proof_for(diff)
        proof["nodes"].append(_node("orphan", "ROOT_OBSERVE", {}, []))
        body = dict(proof)
        body.pop("proof_digest")
        proof["proof_digest"] = digest(body)
        entry = self.ledger.apply_authorized(diff, proof)
        self.assertEqual(entry.refuse_reason, "LINEAGE_PROOF_CONTAINS_UNREACHABLE_NODE")


if __name__ == "__main__":
    unittest.main()
