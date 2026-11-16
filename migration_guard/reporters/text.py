"""Human-readable terminal report. Every number comes from the AnalysisResult."""

from __future__ import annotations

from migration_guard.models import AnalysisResult, Finding, Severity


def _tag(f: Finding) -> str:
    if f.suppressed:
        return "SUPPRESSED"
    return "BLOCKING" if f.blocking else "WARNING"


def render_text(result: AnalysisResult) -> str:
    out: list[str] = []
    order = sorted(result.findings, key=lambda f: (f.file, f.line, f.rule_id))

    for f in order:
        target = f.table or "-"
        if f.object and f.object != f.table:
            target = f"{target}.{f.object}"
        out.append(
            f"{f.file}:{f.line}  {f.rule_id}  {f.severity.value}  {f.operation}  "
            f"{target}  [{_tag(f)}]"
        )
        out.append(f"    {f.message}")
        if f.suppressed:
            out.append(f"    Suppressed: {f.suppression_reason}")
        else:
            out.append(f"    Fix: {f.recommendation}")
        out.append("")

    for e in result.errors:
        where = e.file or "(run)"
        if e.line:
            where = f"{where}:{e.line}"
        out.append(f"{where}  ERROR  {e.kind}")
        out.append(f"    {e.message}")
        out.append("")

    s = result.summary
    sev = ", ".join(f"{k.value} {s.by_severity.get(k, 0)}" for k in reversed(list(Severity)))
    out.append("-" * 60)
    out.append(
        f"Files: {s.files}   Statements: {s.statements}   Findings: {s.findings} "
        f"(blocking {s.blocking}, suppressed {s.suppressed})   Errors: {s.errors}"
    )
    out.append(f"By severity: {sev}")
    out.append(f"Policy: block at {result.fail_on.value} and above")
    out.append(f"Result: {result.verdict.value}")
    return "\n".join(out) + "\n"
