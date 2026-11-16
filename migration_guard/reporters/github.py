"""GitHub Actions output.

Workflow commands (``::error file=...,line=...::message``) become inline
annotations on the pull request diff. The Markdown summary is appended to the
file named by $GITHUB_STEP_SUMMARY and shows on the run's summary page.
"""

from __future__ import annotations

from migration_guard.models import AnalysisResult, Severity


def _escape_data(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_prop(value: str) -> str:
    return _escape_data(value).replace(":", "%3A").replace(",", "%2C")


def _command(level: str, message: str, file: str | None, line: int | None, title: str) -> str:
    props = []
    if file:
        props.append(f"file={_escape_prop(file)}")
    if line:
        props.append(f"line={line}")
    props.append(f"title={_escape_prop(title)}")
    return f"::{level} {','.join(props)}::{_escape_data(message)}"


def render_github(result: AnalysisResult) -> str:
    lines = []
    for f in sorted(result.findings, key=lambda f: (f.file, f.line, f.rule_id)):
        if f.suppressed:
            level, extra = "notice", f"Suppressed: {f.suppression_reason}"
        else:
            level = "error" if f.blocking else "warning"
            extra = f"Fix: {f.recommendation}"
        title = f"{f.rule_id} {f.severity.value}: {f.operation}"
        lines.append(_command(level, f"{f.message}\n{extra}", f.file, f.line, title))
    for e in result.errors:
        lines.append(_command("error", e.message, e.file, e.line, f"MigrationGuard {e.kind}"))

    s = result.summary
    lines.append(
        f"MigrationGuard: {result.verdict.value} - {s.files} file(s), {s.statements} "
        f"statement(s), {s.findings} finding(s), {s.blocking} blocking, {s.errors} error(s)"
    )
    return "\n".join(lines) + "\n"


def _md(value: str | None) -> str:
    return (value or "-").replace("|", "\\|").replace("\n", " ")


def render_step_summary(result: AnalysisResult) -> str:
    s = result.summary
    out = [
        f"## MigrationGuard: {result.verdict.value}",
        "",
        f"{s.files} file(s), {s.statements} statement(s), {s.findings} finding(s) "
        f"({s.blocking} blocking, {s.suppressed} suppressed), {s.errors} error(s). "
        f"Policy blocks at **{result.fail_on.value}** and above.",
        "",
    ]
    if result.findings:
        out += [
            "| Status | Rule | Severity | Location | Operation | Message |",
            "|---|---|---|---|---|---|",
        ]
        rank = {sev: i for i, sev in enumerate(Severity)}
        for f in sorted(result.findings, key=lambda f: (-rank[f.severity], f.file, f.line)):
            status = "suppressed" if f.suppressed else ("blocking" if f.blocking else "warning")
            out.append(
                f"| {status} | {f.rule_id} | {f.severity.value} | `{f.file}:{f.line}` | "
                f"{f.operation} | {_md(f.message)} |"
            )
        out.append("")
    if result.errors:
        out += ["### Errors", ""]
        for e in result.errors:
            loc = f"`{e.file}:{e.line}`" if e.file and e.line else f"`{e.file or 'run'}`"
            out.append(f"- **{e.kind}** {loc}: {_md(e.message)}")
        out.append("")
    return "\n".join(out) + "\n"
