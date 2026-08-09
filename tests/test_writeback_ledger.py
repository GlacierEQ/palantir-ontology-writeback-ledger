
from __future__ import annotations
import unittest
from src.writeback_ledger import (
    DiffOp, ObjectSnapshot, OntologyWritebackLedger, SignMode, WritebackDiff, ApplyStatus,
)

class LedgerLeveledTests(unittest.TestCase):
    def setUp(self):
        self.schema = "onto-v3"
        self.led = OntologyWritebackLedger(self.schema, SignMode.HUMAN_AGENT)
        self.base = ObjectSnapshot("Aircraft", "A-1", {"status": "ground", "tail": "N1"}, self.schema)
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
        e = self.led.apply(self._diff())
        self.assertEqual(e.status, ApplyStatus.APPLIED)

    def test_schema_drift_refuses(self):
        bad = ObjectSnapshot("Aircraft", "A-1", {"status": "ground", "tail": "N1"}, "old-schema")
        e = self.led.apply(self._diff(base=bad))
        self.assertEqual(e.refuse_reason, "SCHEMA_DRIFT")

    def test_missing_human_refuses(self):
        e = self.led.apply(self._diff(signatures=("agent:scout", "agent:other")))
        self.assertEqual(e.refuse_reason, "INSUFFICIENT_SIGN_OFF")

    def test_stale_base_refuses(self):
        self.led.apply(self._diff())
        e = self.led.apply(self._diff(diff_id="d2", parent_ledger_hash=self.led.tip))
        self.assertEqual(e.refuse_reason, "BASE_STALE")

    def test_parent_mismatch(self):
        e = self.led.apply(self._diff(parent_ledger_hash="deadbeef"))
        self.assertEqual(e.refuse_reason, "PARENT_MISMATCH")

    def test_bad_path_refuses(self):
        e = self.led.apply(self._diff(ops=(DiffOp("status.nested", "set", 1),), parent_ledger_hash=self.led.tip))
        self.assertTrue(e.refuse_reason and e.refuse_reason.startswith("BAD_PATH"))

    def test_too_many_ops(self):
        ops = tuple(DiffOp(f"f{i}", "set", i) for i in range(40))
        e = self.led.apply(self._diff(ops=ops, parent_ledger_hash=self.led.tip))
        self.assertEqual(e.refuse_reason, "TOO_MANY_OPS")

    def test_batch_all_or_nothing(self):
        b2 = ObjectSnapshot("Pilot", "P-1", {"role": "pilot"}, self.schema)
        self.led.upsert_base(b2)
        d_ok = self._diff(diff_id="ok", parent_ledger_hash=self.led.tip)
        d_bad = WritebackDiff(
            diff_id="bad",
            base=b2,
            ops=(DiffOp("role", "set", "x"),),
            proposed_by="agent:scout",
            authority="mission-ops",
            mode=SignMode.HUMAN_AGENT,
            signatures=("agent:only",),  # insufficient
            parent_ledger_hash=self.led.tip,
        )
        results = self.led.apply_batch([d_ok, d_bad])
        self.assertTrue(any(r.status is ApplyStatus.REFUSED for r in results))
        # first object should be rolled back
        cur = self.led.get("Aircraft", "A-1")
        assert cur is not None
        self.assertEqual(cur.properties["status"], "ground")

    def test_reverse_diff_undo(self):
        d = self._diff()
        e = self.led.apply(d)
        self.assertEqual(e.status, ApplyStatus.APPLIED)
        cur = self.led.get("Aircraft", "A-1")
        assert cur is not None
        undo = self.led.reverse_diff(d, cur)
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
        e2 = self.led.apply(undo)
        self.assertEqual(e2.status, ApplyStatus.APPLIED)
        cur2 = self.led.get("Aircraft", "A-1")
        assert cur2 is not None
        self.assertEqual(cur2.properties["status"], "ground")

if __name__ == "__main__":
    unittest.main()
