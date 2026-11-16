"""Read ``-- migration-guard: ignore MGxxx reason="..."`` comments.

This is the only place MigrationGuard reads comments. Detection itself never
looks at comment text, only at the parsed AST.

A suppression applies to the statement directly below it. Several directive
lines may be stacked, but a blank line or a non-comment line ends the block.
A reason is mandatory: suppressing a safety check should leave a record of why.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from migration_guard.rules import rule_ids

MARKER = "migration-guard:"

_DIRECTIVE = re.compile(
    r"""^--\s*migration-guard:\s*ignore\s+
        (?P<ids>MG\d{3}(?:\s*,\s*MG\d{3})*)
        (?:\s+reason\s*=\s*"(?P<reason>[^"]*)")?
        \s*$""",
    re.VERBOSE,
)


class SuppressionError(Exception):
    def __init__(self, message: str, line: int) -> None:
        super().__init__(message)
        self.message = message
        self.line = line


@dataclass(frozen=True)
class Suppression:
    rule_id: str
    reason: str
    line: int


def parse_suppressions(text: str) -> dict[int, list[Suppression]]:
    """Return {line_number: [suppressions on that line]} and validate every directive."""
    known = rule_ids()
    found: dict[int, list[Suppression]] = {}
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line.startswith("--") or MARKER not in line:
            continue
        m = _DIRECTIVE.match(line)
        if not m:
            raise SuppressionError(
                "Malformed suppression. Expected: "
                '-- migration-guard: ignore MG003 reason="why this is safe"',
                lineno,
            )
        reason = (m.group("reason") or "").strip()
        if not reason:
            raise SuppressionError(
                'Suppression needs a reason, e.g. reason="column unused since v2.3"', lineno
            )
        ids = [i.strip() for i in m.group("ids").split(",")]
        for rule_id in ids:
            if rule_id not in known:
                raise SuppressionError(f"Suppression names unknown rule {rule_id}", lineno)
        found[lineno] = [Suppression(r, reason, lineno) for r in ids]
    return found


def suppressions_for_statement(
    text_lines: list[str], directives: dict[int, list[Suppression]], statement_line: int
) -> dict[str, Suppression]:
    """Collect directives from the comment block directly above ``statement_line``."""
    result: dict[str, Suppression] = {}
    lineno = statement_line - 1
    while lineno >= 1:
        content = text_lines[lineno - 1].strip()
        if not content.startswith("--"):
            break
        for s in directives.get(lineno, ()):
            result.setdefault(s.rule_id, s)
        lineno -= 1
    return result
