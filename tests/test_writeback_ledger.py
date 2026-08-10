from __future__ import annotations

import unittest

from src.writeback_ledger import (
    ApplyStatus,
    DiffOp,
    ObjectSnapshot,
    OntologyWritebackLedger,
    SignMode,
    WritebackDiff,
)


class LedgerLeveledTests(unittest.TestCase):
    def setUp(self):
        self.schema = "onto-v3"
        self.led = OntologyWritebackLedger(self.schema, SignMode.HUMAN_AGENT)
        self.base = ObjectSnapshot(
            "Aircraft", "A-1", {"status": "ground", "tail": "N1"}, self.schema
        )
        self.led.upsert_base(self.base)

    def _diff(self, **kw):
        defaults = dict(
            diff_id="d1",
            base=self.base,
            ops=(DiffOp("status", "set", "airborne"),),
            proposed_by="agent:scout",
            authority="mission-ops",
            mode=SignMode.HUMAN_AGENT,
            signatures=("human:ada", "agent:scout"),
            parent_ledger_hash=self.led.tip,
        )
        defaults.update(kw)
        return WritebackDiff(**defaults)

    def test_apply_happy(self):
        entry = self.led.apply(self._diff())
        self.assertEqual(entry.status, ApplyStatus.APPLIED)

    def test_schema_drift_refuses(self):
        bad = ObjectSnapshot(
            "Aircraft", "A-1", {"status": "ground", "tail": "N1"}, "old-schema"
        )
        entry = self.led.apply(self._diff(base=bad))
        self.assertEqual(entry.refuse_reason, "SCHEMA_DRIFT")

    def test_current_object_schema_drift_refuses(self):
        bad_current = ObjectSnapshot(
            "Aircraft", "A-1", {"status": "ground", "tail": "N1"}, "old-schema"
        )
        self.led.upsert_base(bad_current)
        entry = self.led.apply(self._diff())
        self.assertEqual(entry.refuse_reason, "SCHEMA_DRIFT")

    def test_missing_human_refuses(self):
        entry = self.led.apply(
            self._diff(signatures=("agent:scout", "agent:other"))
        )
        self.assertEqual(entry.refuse_reason, "INSUFFICIENT_SIGN_OFF")

    def test_empty_authority_refuses(self):
        entry = self.led.apply(self._diff(authority=""))
        self.assertEqual(entry.refuse_reason, "AUTHORITY_REQUIRED")

    def test_empty_proposer_refuses(self):
        entry = self.led.apply(self._diff(proposed_by=""))
        self.assertEqual(entry.refuse_reason, "PROPOSER_REQUIRED")

    def test_stale_base_refuses(self):
        self.led.apply(self._diff())
        entry = self.led.apply(
            self._diff(diff_id="d2", parent_ledger_hash=self.led.tip)
        )
        self.assertEqual(entry.refuse_reason, "BASE_STALE")

    def test_duplicate_diff_id_is_one_shot(self):
        first = self.led.apply(self._diff())
        self.assertEqual(first.status, ApplyStatus.APPLIED)
        current = self.led.get("Aircraft", "A-1")
        assert current is not None
        replay = self._diff(
            base=current,
            ops=(DiffOp("status", "set", "taxi"),),
            parent_ledger_hash=self.led.tip,
        )
        second = self.led.apply(replay)
        self.assertEqual(second.refuse_reason, "DUPLICATE_DIFF_ID")
        self.assertEqual(self.led.get("Aircraft", "A-1"), current)

    def test_refused_diff_id_cannot_be_repurposed(self):
        refused = self.led.apply(self._diff(authority=""))
        self.assertEqual(refused.refuse_reason, "AUTHORITY_REQUIRED")
        # Structurally invalid metadata is not reserved because it never established
        # a valid immutable attempt identity.
        allowed = self.led.apply(self._diff(authority="mission-ops"))
        self.assertEqual(allowed.status, ApplyStatus.APPLIED)

    def test_parent_mismatch(self):
        entry = self.led.apply(self._diff(parent_ledger_hash="deadbeef"))
        self.assertEqual(entry.refuse_reason, "PARENT_MISMATCH")

    def test_bad_path_refuses(self):
        entry = self.led.apply(
            self._diff(
                ops=(DiffOp("status.nested", "set", 1),),
                parent_ledger_hash=self.led.tip,
            )
        )
        self.assertTrue(
            entry.refuse_reason and entry.refuse_reason.startswith("BAD_PATH")
        )

    def test_too_many_ops(self):
        ops = tuple(DiffOp(f"f{i}", "set", i) for i in range(40))
        entry = self.led.apply(self._diff(ops=ops, parent_ledger_hash=self.led.tip))
        self.assertEqual(entry.refuse_reason, "TOO_MANY_OPS")

    def test_batch_all_or_nothing(self):
        second = ObjectSnapshot("Pilot", "P-1", {"role": "pilot"}, self.schema)
        self.led.upsert_base(second)
        d_ok = self._diff(diff_id="ok", parent_ledger_hash=self.led.tip)
        d_bad = WritebackDiff(
            diff_id="bad",
            base=second,
            ops=(DiffOp("role", "set", "x"),),
            proposed_by="agent:scout",
            authority="mission-ops",
            mode=SignMode.HUMAN_AGENT,
            signatures=("agent:only",),
            parent_ledger_hash=self.led.tip,
        )
        results = self.led.apply_batch([d_ok, d_bad])
        self.assertTrue(any(r.status is ApplyStatus.REFUSED for r in results))
        cur = self.led.get("Aircraft", "A-1")
        assert cur is not None
        self.assertEqual(cur.properties["status"], "ground")
        self.assertEqual(len(self.led.replay_hashes()), 1)

    def test_batch_never_silently_refreshes_stale_base(self):
        first = self._diff(diff_id="batch-1")
        second = self._diff(
            diff_id="batch-2",
            ops=(DiffOp("tail", "set", "N2"),),
        )
        results = self.led.apply_batch([first, second])
        self.assertEqual(results[0].status, ApplyStatus.APPLIED)
        self.assertEqual(results[1].refuse_reason, "BASE_STALE")
        cur = self.led.get("Aircraft", "A-1")
        assert cur is not None
        self.assertEqual(cur.properties, self.base.properties)
        self.assertEqual(len(self.led.replay_hashes()), 1)

    def test_reverse_diff_undo(self):
        diff = self._diff()
        entry = self.led.apply(diff)
        self.assertEqual(entry.status, ApplyStatus.APPLIED)
        cur = self.led.get("Aircraft", "A-1")
        assert cur is not None
        undo = self.led.reverse_diff(diff, cur)
        undo = WritebackDiff(
            diff_id=undo.diff_id,
            base=cur,
            ops=undo.ops,
            proposed_by=undo.proposed_by,
            authority=undo.authority,
            mode=undo.mode,
            signatures=undo.signatures,
            parent_ledger_hash=self.led.tip,
        )
        entry2 = self.led.apply(undo)
        self.assertEqual(entry2.status, ApplyStatus.APPLIED)
        cur2 = self.led.get("Aircraft", "A-1")
        assert cur2 is not None
        self.assertEqual(cur2.properties["status"], "ground")


if __name__ == "__main__":
    unittest.main()
