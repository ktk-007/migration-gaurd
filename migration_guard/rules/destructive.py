"""Rules for operations that destroy data or break running application code."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from pglast.enums import AlterTableType, ObjectType

from migration_guard.models import Category, Severity
from migration_guard.rules.base import (
    EXPAND_AND_CONTRACT,
    Hit,
    Rule,
    qualified_name,
    relation_name,
)
from migration_guard.rules.registry import register


@register
class DropTable(Rule):
    id = "MG001"
    title = "DROP TABLE"
    severity = Severity.CRITICAL
    category = Category.DATA_LOSS
    node_types = ("DropStmt",)

    def check(self, node: Any) -> Iterator[Hit]:
        if node.removeType != ObjectType.OBJECT_TABLE:
            return
        # DROP TABLE a, b drops two tables: report each one.
        for parts in node.objects or ():
            name = qualified_name(parts)
            yield Hit(
                operation="DROP_TABLE",
                table=name,
                object=name,
                message=f"Dropping table '{name}' permanently deletes the table and all its data.",
                recommendation=(
                    "Confirm no service still reads or writes it, take a backup or archive "
                    "the data, and drop it in a separate, reviewed migration."
                ),
            )


@register
class Truncate(Rule):
    id = "MG002"
    title = "TRUNCATE"
    severity = Severity.CRITICAL
    category = Category.DATA_LOSS
    node_types = ("TruncateStmt",)

    def check(self, node: Any) -> Iterator[Hit]:
        for rel in node.relations or ():
            name = relation_name(rel)
            yield Hit(
                operation="TRUNCATE",
                table=name,
                message=f"TRUNCATE removes every row from '{name}' instantly, with no WHERE.",
                recommendation=(
                    "Migrations should not wipe tables. If the data really must go, archive "
                    "it first and do it as a reviewed, one-off operation."
                ),
            )


@register
class DropColumn(Rule):
    id = "MG003"
    title = "DROP COLUMN"
    severity = Severity.HIGH
    category = Category.DATA_LOSS
    node_types = ("AlterTableStmt",)

    def check(self, node: Any) -> Iterator[Hit]:
        table = relation_name(node.relation)
        for cmd in node.cmds or ():
            if cmd.subtype == AlterTableType.AT_DropColumn:
                yield Hit(
                    operation="DROP_COLUMN",
                    table=table,
                    object=cmd.name,
                    message=(
                        f"Dropping column '{cmd.name}' from '{table}' permanently removes its "
                        "data, and application versions still running may read it."
                    ),
                    recommendation=EXPAND_AND_CONTRACT,
                )


@register
class Rename(Rule):
    id = "MG010"
    title = "RENAME COLUMN or TABLE"
    severity = Severity.MEDIUM
    category = Category.COMPATIBILITY
    node_types = ("RenameStmt",)

    def check(self, node: Any) -> Iterator[Hit]:
        table = relation_name(node.relation)
        if node.renameType == ObjectType.OBJECT_COLUMN:
            yield Hit(
                operation="RENAME_COLUMN",
                table=table,
                object=node.subname,
                message=(
                    f"Renaming column '{node.subname}' to '{node.newname}' breaks every running "
                    "query that uses the old name."
                ),
                recommendation=EXPAND_AND_CONTRACT,
            )
        elif node.renameType == ObjectType.OBJECT_TABLE:
            yield Hit(
                operation="RENAME_TABLE",
                table=table,
                object=table,
                message=(
                    f"Renaming table '{table}' to '{node.newname}' breaks every running "
                    "query that uses the old name."
                ),
                recommendation=EXPAND_AND_CONTRACT,
            )
