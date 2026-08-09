"""Ontology writeback diff ledger — typed mutations with fail-closed apply."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


def digest(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


class SignMode(str, Enum):
    HUMAN_AGENT = "HUMAN_AGENT"
    TWO_AGENT = "TWO_AGENT"


class ApplyStatus(str, Enum):
    APPLIED = "APPLIED"
    REFUSED = "REFUSED"


@dataclass(frozen=True)
class ObjectSnapshot:
    object_type: str
    object_id: str
    properties: Mapping[str, Any]
    schema_fingerprint: str

    def content_digest(self) -> str:
        return digest({"type": self.object_type, "id": self.object_id, "props": dict(self.properties)})


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


class OntologyWritebackLedger:
    def __init__(self, required_schema: str, mode: SignMode = SignMode.HUMAN_AGENT):
        self.required_schema = required_schema
        self.mode = mode
        self._objects: dict[tuple[str, str], ObjectSnapshot] = {}
        self._entries: list[LedgerEntry] = []
        self._tip = digest({"genesis": True})

    @property
    def tip(self) -> str:
        return self._tip

    def upsert_base(self, snap: ObjectSnapshot) -> None:
        self._objects[(snap.object_type, snap.object_id)] = snap

    def _signatures_ok(self, diff: WritebackDiff) -> bool:
        sigs = set(diff.signatures)
        if diff.mode is SignMode.HUMAN_AGENT:
            return any(s.startswith("human:") for s in sigs) and any(s.startswith("agent:") for s in sigs)
        if diff.mode is SignMode.TWO_AGENT:
            agents = [s for s in sigs if s.startswith("agent:")]
            return len(set(agents)) >= 2
        return False

    def apply(self, diff: WritebackDiff) -> LedgerEntry:
        reason = None
        status = ApplyStatus.REFUSED
        resulting = None

        if diff.parent_ledger_hash != self._tip:
            reason = "PARENT_MISMATCH"
        elif diff.base.schema_fingerprint != self.required_schema:
            reason = "SCHEMA_DRIFT"
        elif diff.mode != self.mode:
            reason = "MODE_MISMATCH"
        elif not self._signatures_ok(diff):
            reason = "INSUFFICIENT_SIGN_OFF"
        elif not diff.ops:
            reason = "EMPTY_DIFF"
        else:
            key = (diff.base.object_type, diff.base.object_id)
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
                    elif op.op == "delete":
                        props.pop(op.path, None)
                    else:
                        reason = f"BAD_OP:{op.op}"
                        break
                if reason is None:
                    new_snap = ObjectSnapshot(
                        object_type=current.object_type,
                        object_id=current.object_id,
                        properties=props,
                        schema_fingerprint=current.schema_fingerprint,
                    )
                    self._objects[key] = new_snap
                    resulting = new_snap.content_digest()
                    status = ApplyStatus.APPLIED

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
        )
        self._entries.append(entry)
        if status is ApplyStatus.APPLIED:
            self._tip = ledger_hash
        return entry

    def replay_hashes(self) -> list[str]:
        return [e.ledger_hash for e in self._entries]
