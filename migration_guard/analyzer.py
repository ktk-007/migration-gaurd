"""Run every enabled rule over every statement and apply the policy.

The analyzer knows nothing about individual rules: it asks the registry for
them. Adding a rule therefore never changes this file.
"""

from __future__ import annotations

from pathlib import Path

from migration_guard import __version__
from migration_guard.config import Config
from migration_guard.models import (
    AnalysisError,
    AnalysisResult,
    Finding,
    Severity,
    Verdict,
)
from migration_guard.parser import ParsedFile, ParseFailure, parse_text, read_sql
from migration_guard.rules import all_rules
from migration_guard.scanner import display_path
from migration_guard.suppressions import (
    SuppressionError,
    parse_suppressions,
    suppressions_for_statement,
)


def analyze_parsed(parsed: ParsedFile, config: Config) -> list[Finding]:
    """Findings for one already-parsed file. Raises SuppressionError on a bad directive."""
    directives = parse_suppressions(parsed.text)
    lines = parsed.text.splitlines()
    rules = [r for r in all_rules() if config.is_enabled(r.id)]
    findings: list[Finding] = []

    for stmt in parsed.statements:
        suppressed = suppressions_for_statement(lines, directives, stmt.line)
        for rule in rules:
            if not rule.applies_to(stmt.node):
                continue
            severity = config.severity_for(rule.id, rule.severity)
            for hit in rule.check(stmt.node):
                sup = suppressed.get(rule.id)
                findings.append(
                    Finding(
                        rule_id=rule.id,
                        severity=severity,
                        category=rule.category,
                        operation=hit.operation,
                        table=hit.table,
                        object=hit.object,
                        file=parsed.path,
                        statement_index=stmt.index,
                        line=stmt.line,
                        blocking=sup is None and severity >= config.fail_on,
                        suppressed=sup is not None,
                        suppression_reason=sup.reason if sup else None,
                        message=hit.message,
                        recommendation=hit.recommendation,
                    )
                )
    return findings


def analyze_files(files: list[Path], config: Config) -> AnalysisResult:
    result = AnalysisResult(tool_version=__version__, fail_on=config.fail_on)

    for path in files:
        shown = display_path(path)
        if config.is_ignored(shown):
            continue
        result.files.append(shown)
        result.summary.files += 1

        try:
            text = read_sql(path)
        except (OSError, UnicodeDecodeError) as exc:
            result.errors.append(AnalysisError(kind="READ_ERROR", file=shown, message=str(exc)))
            continue

        try:
            parsed = parse_text(text, shown)
        except ParseFailure as exc:
            result.errors.append(
                AnalysisError(kind="PARSE_ERROR", file=shown, line=exc.line, message=exc.message)
            )
            continue

        result.summary.statements += len(parsed.statements)
        try:
            result.findings.extend(analyze_parsed(parsed, config))
        except SuppressionError as exc:
            result.errors.append(
                AnalysisError(
                    kind="SUPPRESSION_ERROR", file=shown, line=exc.line, message=exc.message
                )
            )

    return finalize(result)


def finalize(result: AnalysisResult) -> AnalysisResult:
    """Compute the summary, verdict and exit code from the findings and errors."""
    s = result.summary
    s.findings = len(result.findings)
    s.blocking = sum(f.blocking for f in result.findings)
    s.suppressed = sum(f.suppressed for f in result.findings)
    s.errors = len(result.errors)
    s.by_severity = {sev: 0 for sev in Severity}
    for f in result.findings:
        s.by_severity[f.severity] += 1

    if result.errors:
        result.verdict, result.exit_code = Verdict.ERROR, 2
    elif s.blocking:
        result.verdict, result.exit_code = Verdict.BLOCKED, 1
    else:
        result.verdict, result.exit_code = Verdict.PASSED, 0
    return result
