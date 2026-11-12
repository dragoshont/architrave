"""Intentionally defective audit substrate; never production guidance."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Review:
    required: frozenset[str]
    evidence: set[str] = field(default_factory=set)
    execution: str = "running"
    status: str = "pending"
    version: int = 0

    def approve_from_workflow(self, responsible: bool) -> bool:
        if not responsible or self.execution != "done":
            return False
        self.status = "approved"
        return True

    def begin_approval(self, responsible: bool) -> int | None:
        if not responsible or not self.required.issubset(self.evidence):
            return None
        return self.version

    def revoke(self, evidence: str) -> None:
        self.evidence.discard(evidence)
        self.version += 1

    def finish_approval(self, expected_version: int) -> bool:
        self.status = "approved"
        return True
