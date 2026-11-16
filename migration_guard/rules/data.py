"""Rules for data changes that are almost always mistakes in a migration."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from migration_guard.models import Category, Severity
from migration_guard.rules.base import Hit, Rule, relation_name
from migration_guard.rules.registry import register


@register
class UnboundedDeleteOrUpdate(Rule):
    id = "MG007"
    title = "DELETE or UPDATE without WHERE"
    severity = Severity.HIGH
    category = Category.DATA_INTEGRITY
    node_types = ("DeleteStmt", "UpdateStmt")

    def check(self, node: Any) -> Iterator[Hit]:
        if node.whereClause is not None:
            return
        verb = "DELETE" if type(node).__name__ == "DeleteStmt" else "UPDATE"
        table = relation_name(node.relation)
        yield Hit(
            operation=f"{verb}_ALL_ROWS",
            table=table,
            message=f"{verb} on '{table}' has no WHERE clause, so it touches every row.",
            recommendation=(
                "Add a WHERE clause. If every row really must change, do it in batches and "
                "say so explicitly with a suppression comment and a reason."
            ),
        )
