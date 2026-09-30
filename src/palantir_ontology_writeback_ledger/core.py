"""Enterprise Data Platform & Authority Governance — Core Module"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

class Permission(Enum):
    READ = auto()
    WRITE = auto()
    EXECUTE = auto()
    ADMIN = auto()

@dataclass
class DataObject:
    """A tracked data object with lineage."""
    object_id: str
    object_type: str
    owner: str
    lineage: list[str] = field(default_factory=list)

    def add_lineage(self, source_id: str) -> None:
        if source_id not in self.lineage:
            self.lineage.append(source_id)

    @property
    def lineage_depth(self) -> int:
        return len(self.lineage)


class AuthorityMatrix:
    """Access control matrix for data objects."""

    def __init__(self):
        self._grants: dict[tuple[str, str], set[Permission]] = {{}}

    def grant(self, principal: str, object_id: str, perm: Permission) -> None:
        key = (principal, object_id)
        if key not in self._grants:
            self._grants[key] = set()
        self._grants[key].add(perm)

    def revoke(self, principal: str, object_id: str, perm: Permission) -> None:
        key = (principal, object_id)
        if key in self._grants:
            self._grants[key].discard(perm)

    def check(self, principal: str, object_id: str, perm: Permission) -> bool:
        return perm in self._grants.get((principal, object_id), set())

    def audit_log(self, principal: str) -> dict[str, set[Permission]]:
        result = {{}}
        for (p, obj), perms in self._grants.items():
            if p == principal:
                result[obj] = perms
        return result


class IntentCompiler:
    """Compiles high-level intents into actionable query plans."""

    def __init__(self):
        self._rules: list[tuple[str, callable]] = []

    def register_rule(self, intent_pattern: str, handler: callable) -> None:
        self._rules.append((intent_pattern, handler))

    def compile(self, intent: str) -> Optional[dict]:
        for pattern, handler in self._rules:
            if pattern.lower() in intent.lower():
                return handler(intent)
        return None

