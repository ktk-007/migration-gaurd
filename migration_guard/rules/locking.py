"""Rules for operations that take heavy locks or rewrite whole tables."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from pglast.enums import AlterTableType, ConstrType

from migration_guard.models import Category, Severity
from migration_guard.rules.base import Hit, Rule, relation_name
from migration_guard.rules.registry import register

# Constraints that make PostgreSQL fill a new column for existing rows.
_FILLS_VALUE = {ConstrType.CONSTR_DEFAULT, ConstrType.CONSTR_IDENTITY, ConstrType.CONSTR_GENERATED}


@register
class AlterColumnType(Rule):
    id = "MG004"
    title = "ALTER COLUMN ... TYPE"
    severity = Severity.HIGH
    category = Category.LOCKING
    node_types = ("AlterTableStmt",)

    def check(self, node: Any) -> Iterator[Hit]:
        table = relation_name(node.relation)
        for cmd in node.cmds or ():
            if cmd.subtype == AlterTableType.AT_AlterColumnType:
                yield Hit(
                    operation="ALTER_COLUMN_TYPE",
                    table=table,
                    object=cmd.name,
                    message=(
                        f"Changing the type of '{table}.{cmd.name}' can rewrite the whole table "
                        "under an ACCESS EXCLUSIVE lock, and may fail or truncate existing data."
                    ),
                    recommendation=(
                        "Add a new column with the new type, backfill it in batches, switch the "
                        "application over, then drop the old column later."
                    ),
                )


@register
class AddColumnNotNullNoDefault(Rule):
    id = "MG005"
    title = "ADD COLUMN NOT NULL without DEFAULT"
    severity = Severity.HIGH
    category = Category.LOCKING
    node_types = ("AlterTableStmt",)

    def check(self, node: Any) -> Iterator[Hit]:
        table = relation_name(node.relation)
        for cmd in node.cmds or ():
            if cmd.subtype != AlterTableType.AT_AddColumn or cmd.def_ is None:
                continue
            col = cmd.def_
            kinds = {c.contype for c in (col.constraints or ())}
            not_null = col.is_not_null or ConstrType.CONSTR_NOTNULL in kinds
            if not_null and not (kinds & _FILLS_VALUE):
                yield Hit(
                    operation="ADD_COLUMN_NOT_NULL",
                    table=table,
                    object=col.colname,
                    message=(
                        f"Adding NOT NULL column '{col.colname}' without a DEFAULT fails on any "
                        f"table that already has rows ('{table}')."
                    ),
                    recommendation=(
                        "Add the column as nullable (or with a DEFAULT), backfill existing rows, "
                        "then add the NOT NULL constraint in a later migration."
                    ),
                )


@register
class CreateIndexNotConcurrently(Rule):
    id = "MG006"
    title = "CREATE INDEX without CONCURRENTLY"
    severity = Severity.MEDIUM
    category = Category.LOCKING
    node_types = ("IndexStmt",)

    def check(self, node: Any) -> Iterator[Hit]:
        if node.concurrent:
            return
        table = relation_name(node.relation)
        yield Hit(
            operation="CREATE_INDEX",
            table=table,
            object=node.idxname,
            message=(
                f"Building index '{node.idxname or '(unnamed)'}' on '{table}' without "
                "CONCURRENTLY blocks all writes to the table until the build finishes."
            ),
            recommendation=(
                "Use CREATE INDEX CONCURRENTLY. Note that CONCURRENTLY cannot run inside a "
                "transaction block, which many migration tools use by default, so run it in "
                "its own non-transactional migration."
            ),
        )


@register
class AddConstraintWithoutNotValid(Rule):
    id = "MG008"
    title = "ADD FOREIGN KEY or CHECK without NOT VALID"
    severity = Severity.MEDIUM
    category = Category.LOCKING
    node_types = ("AlterTableStmt",)

    def check(self, node: Any) -> Iterator[Hit]:
        table = relation_name(node.relation)
        for cmd in node.cmds or ():
            if cmd.subtype != AlterTableType.AT_AddConstraint or cmd.def_ is None:
                continue
            con = cmd.def_
            # Only FOREIGN KEY and CHECK support NOT VALID in PostgreSQL.
            if con.contype not in (ConstrType.CONSTR_FOREIGN, ConstrType.CONSTR_CHECK):
                continue
            if con.skip_validation:
                continue
            kind = "FOREIGN KEY" if con.contype == ConstrType.CONSTR_FOREIGN else "CHECK"
            yield Hit(
                operation=f"ADD_{kind.replace(' ', '_')}",
                table=table,
                object=con.conname,
                message=(
                    f"Adding {kind} constraint '{con.conname or '(unnamed)'}' on '{table}' "
                    "validates every existing row while holding a lock."
                ),
                recommendation=(
                    "Add the constraint with NOT VALID, then run "
                    "ALTER TABLE ... VALIDATE CONSTRAINT in a separate migration; "
                    "validation then takes a much lighter lock."
                ),
            )


@register
class SetNotNull(Rule):
    id = "MG009"
    title = "ALTER COLUMN SET NOT NULL"
    severity = Severity.MEDIUM
    category = Category.LOCKING
    node_types = ("AlterTableStmt",)

    def check(self, node: Any) -> Iterator[Hit]:
        table = relation_name(node.relation)
        for cmd in node.cmds or ():
            if cmd.subtype == AlterTableType.AT_SetNotNull:
                yield Hit(
                    operation="SET_NOT_NULL",
                    table=table,
                    object=cmd.name,
                    message=(
                        f"SET NOT NULL on '{table}.{cmd.name}' scans the whole table under an "
                        "ACCESS EXCLUSIVE lock."
                    ),
                    recommendation=(
                        f"Add CHECK ({cmd.name} IS NOT NULL) NOT VALID, run VALIDATE CONSTRAINT "
                        "separately, then SET NOT NULL (PostgreSQL 12+ skips the scan when a "
                        "valid CHECK already proves it), and drop the CHECK."
                    ),
                )
