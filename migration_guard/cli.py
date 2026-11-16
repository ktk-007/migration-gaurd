"""Command-line interface.

Exit codes: 0 = no blocking findings, 1 = blocking findings,
2 = tool, config, git or parse failure (fail closed).
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path

import typer

from migration_guard import __version__
from migration_guard.analyzer import analyze_files, finalize
from migration_guard.config import ConfigError, load_config
from migration_guard.models import AnalysisError, AnalysisResult, Severity
from migration_guard.reporters import (
    render_github,
    render_json,
    render_step_summary,
    render_text,
)
from migration_guard.rules import all_rules
from migration_guard.scanner import ScanError, changed_sql_files, collect_sql_files

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Flag risky PostgreSQL migrations before they reach review.",
)


class OutputFormat(str, Enum):
    text = "text"
    json = "json"
    github = "github"


def _version(value: bool) -> None:
    if value:
        typer.echo(f"migration-guard {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", callback=_version, is_eager=True, help="Show the version and exit."
    ),
) -> None:
    """MigrationGuard: static risk analysis for PostgreSQL migrations."""


def _render(result: AnalysisResult, fmt: OutputFormat) -> str:
    if fmt is OutputFormat.json:
        return render_json(result)
    if fmt is OutputFormat.github:
        return render_github(result)
    return render_text(result)


@app.command()
def check(
    paths: list[Path] = typer.Argument(..., help="Migration files or directories to check."),
    config: Path | None = typer.Option(
        None, "--config", help="Config file (default: ./.migrationguard.yml if present)."
    ),
    fmt: OutputFormat = typer.Option(OutputFormat.text, "--format", help="Report format."),
    output: Path | None = typer.Option(None, "--output", help="Also write the report here."),
    changed_since: str | None = typer.Option(
        None, "--changed-since", help="Only check .sql files changed since this git ref."
    ),
    fail_on: Severity | None = typer.Option(
        None, "--fail-on", help="Block findings at or above this severity (overrides config)."
    ),
) -> None:
    """Analyse migrations and exit 0 (pass), 1 (blocked) or 2 (tool error)."""
    try:
        cfg = load_config(config)
        if fail_on is not None:
            cfg = cfg.model_copy(update={"fail_on": fail_on})
        if changed_since:
            files = changed_sql_files(changed_since, paths)
        else:
            files = collect_sql_files(paths)
        result = analyze_files(files, cfg)
    except ConfigError as exc:
        result = _error_result("CONFIG_ERROR", str(exc), fail_on)
    except ScanError as exc:
        result = _error_result(exc.kind, exc.message, fail_on)

    report = _render(result, fmt)
    typer.echo(report, nl=False)
    if output:
        output.write_text(report, encoding="utf-8")
    if fmt is OutputFormat.github and os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
            fh.write(render_step_summary(result))
    raise typer.Exit(result.exit_code)


def _error_result(kind: str, message: str, fail_on: Severity | None) -> AnalysisResult:
    result = AnalysisResult(tool_version=__version__, fail_on=fail_on or Severity.HIGH)
    result.errors.append(AnalysisError(kind=kind, message=message))
    return finalize(result)


@app.command("rules")
def list_rules() -> None:
    """List every rule with its ID, default severity and description."""
    typer.echo(f"{'ID':<7}{'SEVERITY':<10}{'CATEGORY':<16}TITLE")
    for rule in all_rules():
        typer.echo(f"{rule.id:<7}{rule.severity.value:<10}{rule.category.value:<16}{rule.title}")
