"""The Rule abstraction.

A rule says which AST node types it cares about and, for each matching node,
yields zero or more ``Hit`` objects. It knows nothing about files, line numbers,
policy or suppression: the analyzer adds all of that. This keeps every rule a
small, independently testable class.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, ClassVar

from migration_guard.models import Category, Severity

EXPAND_AND_CONTRACT = (
    "Use expand-and-contract: (1) add the new column/table, (2) deploy code that reads "
    "and writes both, (3) backfill existing rows in batches, (4) switch reads and writes "
    "to the new one, (5) verify nothing uses the old one, (6) remove it in a later migration."
)


@dataclass(frozen=True)
class Hit:
    """What a rule reports. The analyzer turns it into a full Finding."""

    operation: str
    message: str
    recommendation: str
    table: str | None = None
    object: str | None = None


class Rule:
    id: ClassVar[str]
    title: ClassVar[str]
    severity: ClassVar[Severity]
    category: ClassVar[Category]
    node_types: ClassVar[tuple[str, ...]]  # pglast class names, e.g. ("DropStmt",)

    def check(self, node: Any) -> Iterator[Hit]:
        raise NotImplementedError

    def applies_to(self, node: Any) -> bool:
        return type(node).__name__ in self.node_types


def relation_name(range_var: Any) -> str | None:
    """'schema.table' from a pglast RangeVar, or just 'table'."""
    if range_var is None:
        return None
    if getattr(range_var, "schemaname", None):
        return f"{range_var.schemaname}.{range_var.relname}"
    return range_var.relname


def qualified_name(parts: Any) -> str:
    """Join a tuple of pglast String nodes into 'a.b.c'."""
    return ".".join(p.sval for p in parts)
