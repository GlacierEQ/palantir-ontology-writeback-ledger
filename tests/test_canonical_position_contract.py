from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path: str):
    return json.loads((ROOT / path).read_text())


CANONICAL = load("machine/canonical-position.json")
CAPABILITIES = load("machine/capabilities.json")
TARGET = load("machine/target-contract.json")


class CanonicalPositionContractTests(unittest.TestCase):
    def test_repository_owns_only_transactional_writeback(self):
        self.assertEqual(
            CANONICAL["repository"],
            "GlacierEQ/palantir-ontology-writeback-ledger",
        )
        self.assertEqual(CANONICAL["role"], "CANONICAL_SPECIALIST")
        self.assertEqual(CANONICAL["owns"], "transactional_ontology_writeback")
        self.assertIn("action provenance DAG semantics", CANONICAL["does_not_own"])
        self.assertIn("actor/object authorization policy", CANONICAL["does_not_own"])

    def test_regression_lineage_is_preserved(self):
        lineage = CANONICAL["lineage"]
        self.assertEqual(
            lineage["good_implementation_commit"],
            "d3bc776e22d1011015302e96a432104421c1924c",
        )
        self.assertEqual(
            lineage["good_implementation_blob"],
            "4639954800f01ed714daad78a0d3a485183ec3be",
        )
        self.assertEqual(
            lineage["regression_commit"],
            "bca7d82b7a5750a81424d49768079ca19a1fd0e2",
        )
        self.assertIn("truncated", lineage["regression"])

    def test_sibling_relationships_do_not_claim_integration(self):
        relationships = {
            edge["repository"]: edge for edge in CANONICAL["relationships"]
        }
        self.assertFalse(
            relationships["GlacierEQ/palantir-action-lineage-graph"][
                "integration_exercised"
            ]
        )
        self.assertFalse(
            relationships["GlacierEQ/palantir-object-authority-matrix"][
                "integration_exercised"
            ]
        )

    def test_capabilities_are_repository_native(self):
        capabilities = set(CAPABILITIES["capabilities"])
        self.assertNotIn("hyper-scaling", capabilities)
        self.assertIn("schema_fingerprint_guard", capabilities)
        self.assertIn("stale_base_guard", capabilities)
        self.assertIn("one_shot_diff_identity", capabilities)
        self.assertIn("atomic_batch_rollback", capabilities)
        self.assertIn("reverse_diff_undo", capabilities)
        self.assertIn("deterministic_ledger_receipts", capabilities)

    def test_recovery_requires_exact_head_proof_before_state_advance(self):
        self.assertEqual(TARGET["current"]["state"], "PROMOTED")
        self.assertFalse(TARGET["current"]["tested"])
        self.assertTrue(TARGET["current"]["recovery_pending_exact_head_proof"])
        self.assertTrue(TARGET["promotion"]["require_exact_source_sha"])
        self.assertEqual(
            TARGET["promotion"]["next_gate"], "CANONICAL_POSITION_RESOLVED"
        )

    def test_public_truth_boundary_is_explicit(self):
        truth = CAPABILITIES["truth_boundary"]
        self.assertIn("in-memory", truth)
        self.assertIn("not externally authenticated", truth)
        self.assertIn("not claimed", truth)


if __name__ == "__main__":
    unittest.main()
