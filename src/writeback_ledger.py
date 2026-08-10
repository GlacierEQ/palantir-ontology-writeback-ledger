from __future__ import annotations
import hashlib, json, re, threading
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
