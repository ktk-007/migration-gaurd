"""Data models shared by every part of MigrationGuard.

Everything that crosses a module boundary (findings, errors, the final report)
is a Pydantic model, so the JSON output has one well-defined shape and can be
parsed back by other tools.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Severity(str, Enum):
    """How dangerous a finding is. Ordered LOW < MEDIUM < HIGH < CRITICAL.

    Severity only describes risk. Whether a finding *blocks* a PR is decided
    separately by the policy's ``fail_on`` threshold.
    """

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @property
    def rank(self) -> int:
        return _RANK[self]

    def __ge__(self, other: object) -> bool:  # type: ignore[override]
        if not isinstance(other, Severity):
            return NotImplemented
        return self.rank >= other.rank

    def __gt__(self, other: object) -> bool:  # type: ignore[override]
        if not isinstance(other, Severity):
            return NotImplemented
        return self.rank > other.rank

    def __le__(self, other: object) -> bool:  # type: ignore[override]
        if not isinstance(other, Severity):
            return NotImplemented
        return self.rank <= other.rank

    def __lt__(self, other: object) -> bool:  # type: ignore[override]
        if not isinstance(other, Severity):
            return NotImplemented
        return self.rank < other.rank


_RANK = {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2, Severity.CRITICAL: 3}


class Category(str, Enum):
    DATA_LOSS = "DATA_LOSS"
    LOCKING = "LOCKING"
    COMPATIBILITY = "COMPATIBILITY"
    DATA_INTEGRITY = "DATA_INTEGRITY"


class Finding(BaseModel):
    """One risky operation found in one statement."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    severity: Severity
    category: Category
    operation: str
    table: str | None = None
    object: str | None = None
    file: str
    statement_index: int = Field(ge=1, description="1-based position of the statement in its file")
    line: int = Field(ge=1, description="1-based line where the statement starts")
    blocking: bool = False
    suppressed: bool = False
    suppression_reason: str | None = None
    message: str
    recommendation: str


class AnalysisError(BaseModel):
    """Something we could not analyse. Any error makes the run fail closed (exit 2)."""

    model_config = ConfigDict(extra="forbid")

    kind: str  # PARSE_ERROR, READ_ERROR, SUPPRESSION_ERROR, CONFIG_ERROR, GIT_ERROR, PATH_ERROR
    message: str
    file: str | None = None
    line: int | None = None


class Summary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    files: int = 0
    statements: int = 0
    findings: int = 0
    blocking: int = 0
    suppressed: int = 0
    errors: int = 0
    by_severity: dict[Severity, int] = Field(default_factory=lambda: {s: 0 for s in Severity})


class Verdict(str, Enum):
    PASSED = "PASSED"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"


class AnalysisResult(BaseModel):
    """The complete outcome of a run. This is exactly what the JSON report contains."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1"
    tool_version: str
    fail_on: Severity
    files: list[str] = Field(default_factory=list)
    summary: Summary = Field(default_factory=Summary)
    findings: list[Finding] = Field(default_factory=list)
    errors: list[AnalysisError] = Field(default_factory=list)
    verdict: Verdict = Verdict.PASSED
    exit_code: int = 0
