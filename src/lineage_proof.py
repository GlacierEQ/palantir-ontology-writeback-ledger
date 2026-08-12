"""Independent verifier for Action Lineage Graph writeback proof bundles.

This module intentionally does not import the sibling repository. A writeback
consumer must be able to verify the complete proof from the serialized bundle it
received, otherwise the integration would collapse back into process-local trust.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

PROOF_SCHEMA = "glaciereq.action-lineage-proof.v1"
VALID_KINDS = {"ROOT_OBSERVE", "TRANSFORM", "SIDE_EFFECT"}


def digest(obj: object) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def verify_lineage_writeback_proof(
    proof: Mapping[str, Any],
    *,
    object_type: str,
    object_id: str,
    diff_fingerprint: str,
    proposed_by: str,
    authority: str,
    schema_fingerprint: str,
    parent_ledger_hash: str,
) -> tuple[bool, str | None]:
    if proof.get("schema") != PROOF_SCHEMA:
        return False, "PROOF_SCHEMA_MISMATCH"
    tip = proof.get("tip")
    nodes_raw = proof.get("nodes")
    if not isinstance(tip, str) or not tip:
        return False, "PROOF_TIP_REQUIRED"
    if not isinstance(nodes_raw, list) or not nodes_raw:
        return False, "PROOF_NODES_REQUIRED"

    expected_digest = proof.get("proof_digest")
    body = dict(proof)
    body.pop("proof_digest", None)
    if expected_digest != digest(body):
        return False, "PROOF_DIGEST_MISMATCH"

    nodes: dict[str, Mapping[str, Any]] = {}
    fingerprints: dict[str, str] = {}
    for raw in nodes_raw:
        if not isinstance(raw, Mapping):
            return False, "PROOF_NODE_INVALID"
        action_id = raw.get("id")
        kind = raw.get("kind")
        payload = raw.get("payload")
        parents = raw.get("parents")
        if not isinstance(action_id, str) or not action_id:
            return False, "PROOF_NODE_ID_INVALID"
        if action_id in nodes:
            return False, "PROOF_DUPLICATE_NODE"
        if kind not in VALID_KINDS:
            return False, f"PROOF_KIND_INVALID:{action_id}"
        if not isinstance(payload, Mapping) or not isinstance(parents, list) or not all(isinstance(p, str) for p in parents):
            return False, f"PROOF_NODE_SHAPE_INVALID:{action_id}"
        if len(parents) != len(set(parents)):
            return False, f"PROOF_DUPLICATE_PARENT:{action_id}"
        computed = digest(
            {
                "id": action_id,
                "kind": kind,
                "payload": dict(payload),
                "parents": list(parents),
                "attestation": raw.get("attestation"),
            }
        )
        if raw.get("fingerprint") != computed:
            return False, f"PROOF_NODE_FINGERPRINT_MISMATCH:{action_id}"
        nodes[action_id] = raw
        fingerprints[action_id] = computed

    if tip not in nodes:
        return False, "PROOF_TIP_MISSING"

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(action_id: str) -> str | None:
        if action_id in visiting:
            return "PROOF_CYCLE"
        if action_id in visited:
            return None
        visiting.add(action_id)
        raw = nodes[action_id]
        parents = raw["parents"]
        kind = raw["kind"]
        if kind == "ROOT_OBSERVE" and parents:
            return f"PROOF_ROOT_HAS_PARENT:{action_id}"
        if kind != "ROOT_OBSERVE" and not parents:
            return f"PROOF_ORPHAN_NONROOT:{action_id}"
        if kind == "SIDE_EFFECT" and not str(raw.get("attestation") or "").strip():
            return f"PROOF_SIDE_EFFECT_ATTESTATION_MISSING:{action_id}"
        for parent in parents:
            if parent not in nodes:
                return f"PROOF_PARENT_MISSING:{parent}"
            error = visit(parent)
            if error:
                return error
        visiting.remove(action_id)
        visited.add(action_id)
        return None

    error = visit(tip)
    if error:
        return False, error
    if set(nodes) != visited:
        return False, "PROOF_CONTAINS_UNREACHABLE_NODE"

    computed_lineage = digest(
        {
            "tip": tip,
            "nodes": [
                {"id": node_id, "fingerprint": fingerprints[node_id]}
                for node_id in sorted(visited)
            ],
        }
    )
    if proof.get("lineage_fingerprint") != computed_lineage:
        return False, "PROOF_LINEAGE_FINGERPRINT_MISMATCH"

    tip_node = nodes[tip]
    if tip_node.get("kind") != "SIDE_EFFECT":
        return False, "WRITEBACK_PROOF_REQUIRES_SIDE_EFFECT"
    claim = tip_node.get("payload", {}).get("writeback")
    if not isinstance(claim, Mapping):
        return False, "WRITEBACK_CLAIM_REQUIRED"
    if claim.get("authorized") is not True:
        return False, "WRITEBACK_NOT_AUTHORIZED"

    expected = {
        "object_type": object_type,
        "object_id": object_id,
        "diff_fingerprint": diff_fingerprint,
        "proposed_by": proposed_by,
        "authority": authority,
        "schema_fingerprint": schema_fingerprint,
        "parent_ledger_hash": parent_ledger_hash,
    }
    for key, value in expected.items():
        if claim.get(key) != value:
            return False, f"WRITEBACK_BINDING_MISMATCH:{key}"
    return True, None
