
"""Ontology writeback diff ledger — typed mutations with fail-closed apply.

Leveled (L1): multi-object batch apply (all-or-nothing), reverse-diff undo with
authority, tip CAS, path validation, max-ops guard.

Independent reference only — no platform affiliation claimed.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence


def digest(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


class SignMode(str, Enum):
    HUMAN_AGENT = "HUMAN_AGENT"
    TWO_AGENT = "TWO_AGENT"


class ApplyStatus(str, Enum):
    APPLIED = "APPLIED"
    REFUSED = "REFUSED"


_PATH_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class ObjectSnapshot:
    object_type: str
    object_id: str
    properties: Mapping[str, Any]
    schema_fingerprint: str

    def content_digest(self) -> str:
        return digest({"type": self.object_type, "id": self.object_id, "props": dict(self.properties)})

    def key(self) -> tuple[str, str]:
        return (self.object_type, self.object_id)


@dataclass(frozen=True)
class DiffOp:
    path: str
    op: str  # set | delete
    value: Any = None


@dataclass(frozen=True)
class WritebackDiff:
    diff_id: str
    base: ObjectSnapshot
    ops: tuple[DiffOp, ...]
    proposed_by: str
    authority: str
    mode: SignMode
    signatures: tuple[str, ...]
    parent_ledger_hash: str

    def fingerprint(self) -> str:
        return digest(
            {
                "diff_id": self.diff_id,
                "base": self.base.content_digest(),
                "schema": self.base.schema_fingerprint,
                "ops": [(o.path, o.op, o.value) for o in self.ops],
                "proposed_by": self.proposed_by,
                "authority": self.authority,
                "mode": self.mode.value,
                "signatures": list(self.signatures),
                "parent": self.parent_ledger_hash,
            }
        )


@dataclass
class LedgerEntry:
    seq: int
    status: ApplyStatus
    refuse_reason: str | None
    diff_fingerprint: str
    resulting_digest: str | None
    ledger_hash: str
    object_key: tuple[str, str] | None = None


class OntologyWritebackLedger:
    def __init__(
        self,
        required_schema: str,
        mode: SignMode = SignMode.HUMAN_AGENT,
        max_ops: int = 32,
    ):
        self.required_schema = required_schema
        self.mode = mode
        self.max_ops = max_ops
        self._objects: dict[tuple[str, str], ObjectSnapshot] = {}
        self._entries: list[LedgerEntry] = []
        self._tip = digest({"genesis": True})
        self._lock = threading.RLock()

    @property
    def tip(self) -> str:
        return self._tip

    def upsert_base(self, snap: ObjectSnapshot) -> None:
        with self._lock:
            self._objects[snap.key()] = snap

    def get(self, object_type: str, object_id: str) -> ObjectSnapshot | None:
        with self._lock:
            return self._objects.get((object_type, object_id))

    def _signatures_ok(self, diff: WritebackDiff) -> bool:
        sigs = set(diff.signatures)
        if diff.mode is SignMode.HUMAN_AGENT:
            return any(s.startswith("human:") for s in sigs) and any(s.startswith("agent:") for s in sigs)
        if diff.mode is SignMode.TWO_AGENT:
            agents = [s for s in sigs if s.startswith("agent:")]
            return len(set(agents)) >= 2
        return False

    def _validate_ops(self, ops: Sequence[DiffOp]) -> str | None:
        if not ops:
            return "EMPTY_DIFF"
        if len(ops) > self.max_ops:
            return "TOO_MANY_OPS"
        for op in ops:
            if op.op not in ("set", "delete"):
                return f"BAD_OP:{op.op}"
            if not _PATH_RE.match(op.path):
                return f"BAD_PATH:{op.path}"
        return None

    def apply(self, diff: WritebackDiff) -> LedgerEntry:
        with self._lock:
            return self._apply_unlocked(diff)

    def _apply_unlocked(self, diff: WritebackDiff) -> LedgerEntry:
        reason = None
        status = ApplyStatus.REFUSED
        resulting = None
        obj_key = None

        if diff.parent_ledger_hash != self._tip:
            reason = "PARENT_MISMATCH"
        elif diff.base.schema_fingerprint != self.required_schema:
            reason = "SCHEMA_DRIFT"
        elif diff.mode != self.mode:
            reason = "MODE_MISMATCH"
        elif not self._signatures_ok(diff):
            reason = "INSUFFICIENT_SIGN_OFF"
        else:
            reason = self._validate_ops(diff.ops)
            if reason is None:
                key = diff.base.key()
                current = self._objects.get(key)
                if current is None:
                    reason = "UNKNOWN_OBJECT"
                elif current.content_digest() != diff.base.content_digest():
                    reason = "BASE_STALE"
                else:
                    props = dict(current.properties)
                    for op in diff.ops:
                        if op.op == "set":
                            props[op.path] = op.value
                        else:
                            props.pop(op.path, None)
                    new_snap = ObjectSnapshot(
                        object_type=current.object_type,
                        object_id=current.object_id,
                        properties=props,
                        schema_fingerprint=current.schema_fingerprint,
                    )
                    self._objects[key] = new_snap
                    resulting = new_snap.content_digest()
                    status = ApplyStatus.APPLIED
                    obj_key = key
                    reason = None

        seq = len(self._entries) + 1
        entry_body = {
            "seq": seq,
            "status": status.value,
            "refuse_reason": reason,
            "diff": diff.fingerprint(),
            "resulting": resulting,
            "parent": self._tip,
        }
        ledger_hash = digest(entry_body)
        entry = LedgerEntry(
            seq=seq,
            status=status,
            refuse_reason=reason,
            diff_fingerprint=diff.fingerprint(),
            resulting_digest=resulting,
            ledger_hash=ledger_hash,
            object_key=obj_key,
        )
        self._entries.append(entry)
        if status is ApplyStatus.APPLIED:
            self._tip = ledger_hash
        return entry

    def apply_batch(self, diffs: Sequence[WritebackDiff]) -> list[LedgerEntry]:
        """All-or-nothing batch: either every diff applies or none mutate state.

        Note: refused batch still appends a single synthetic refuse marker? 
        We snapshot state and roll back on any failure.
        """
        with self._lock:
            snapshot_objects = dict(self._objects)
            snapshot_tip = self._tip
            snapshot_entries_len = len(self._entries)
            results: list[LedgerEntry] = []
            for d in diffs:
                # force parent to current tip for sequential batch
                d2 = WritebackDiff(
                    diff_id=d.diff_id,
                    base=d.base,
                    ops=d.ops,
                    proposed_by=d.proposed_by,
                    authority=d.authority,
                    mode=d.mode,
                    signatures=d.signatures,
                    parent_ledger_hash=self._tip,
                )
                # refresh base from current objects if same key (for multi-step same object)
                cur = self._objects.get(d.base.key())
                if cur is not None:
                    d2 = WritebackDiff(
                        diff_id=d.diff_id,
                        base=cur,
                        ops=d.ops,
                        proposed_by=d.proposed_by,
                        authority=d.authority,
                        mode=d.mode,
                        signatures=d.signatures,
                        parent_ledger_hash=self._tip,
                    )
                entry = self._apply_unlocked(d2)
                results.append(entry)
                if entry.status is ApplyStatus.REFUSED:
                    # rollback
                    self._objects = snapshot_objects
                    self._tip = snapshot_tip
                    del self._entries[snapshot_entries_len:]
                    return results
            return results

    def reverse_diff(self, applied: WritebackDiff, current: ObjectSnapshot) -> WritebackDiff:
        """Build a reverse diff from an applied forward diff against current snapshot."""
        inverse_ops: list[DiffOp] = []
        base_props = dict(applied.base.properties)
        for op in reversed(applied.ops):
            if op.op == "set":
                if op.path in base_props:
                    inverse_ops.append(DiffOp(op.path, "set", base_props[op.path]))
                else:
                    inverse_ops.append(DiffOp(op.path, "delete"))
            elif op.op == "delete":
                if op.path in base_props:
                    inverse_ops.append(DiffOp(op.path, "set", base_props[op.path]))
        return WritebackDiff(
            diff_id=f"undo:{applied.diff_id}",
            base=current,
            ops=tuple(inverse_ops),
            proposed_by=applied.proposed_by,
            authority=applied.authority,
            mode=applied.mode,
            signatures=applied.signatures,
            parent_ledger_hash=self._tip,
        )

    def replay_hashes(self) -> list[str]:
        with self._lock:
            return [e.ledger_hash for e in self._entries]
