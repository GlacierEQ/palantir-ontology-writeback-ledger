from __future__ import annotations
import unittest
from src.writeback_ledger import (
    DiffOp, ObjectSnapshot, OntologyWritebackLedger, SignMode, WritebackDiff, ApplyStatus
)

class LedgerTests(unittest.TestCase):
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
        self.assertIsNone(e.refuse_reason)

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
        # base snapshot still old content
        self.assertEqual(e.refuse_reason, "BASE_STALE")

    def test_parent_mismatch(self):
        e = self.led.apply(self._diff(parent_ledger_hash="deadbeef"))
        self.assertEqual(e.refuse_reason, "PARENT_MISMATCH")

if __name__ == "__main__":
    unittest.main()
