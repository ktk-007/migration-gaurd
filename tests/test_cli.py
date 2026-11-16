"""End-to-end tests through the real CLI, including exit codes and reporters."""

from __future__ import annotations

import json
import shutil

from typer.testing import CliRunner

from conftest import FIXTURES
from migration_guard import __version__
from migration_guard.cli import app
from migration_guard.models import AnalysisResult

runner = CliRunner()


def run(*args: str):
    return runner.invoke(app, list(args))


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_version():
    r = run("--version")
    assert r.exit_code == 0 and __version__ in r.output


def test_rules_lists_every_rule():
    r = run("rules")
    assert r.exit_code == 0
    for i in range(1, 11):
        assert f"MG{i:03d}" in r.output


def test_safe_fixture_exits_0():
    r = run("check", str(FIXTURES / "safe"))
    assert r.exit_code == 0, r.output
    assert "Result: PASSED" in r.output


def test_blocking_finding_exits_1(in_tmp):
    write(in_tmp / "m" / "0001.sql", "DROP TABLE payments;\n")
    r = run("check", "m")
    assert r.exit_code == 1
    assert "MG001" in r.output and "Result: BLOCKED" in r.output
    assert "m/0001.sql:1" in r.output


def test_parse_error_exits_2(in_tmp):
    write(in_tmp / "m" / "0001.sql", "DROP TABEL payments;\n")
    r = run("check", "m")
    assert r.exit_code == 2
    assert "PARSE_ERROR" in r.output


def test_parse_error_wins_over_findings(in_tmp):
    write(in_tmp / "m" / "0001.sql", "DROP TABLE a;\n")
    write(in_tmp / "m" / "0002.sql", "garbage here;\n")
    assert run("check", "m").exit_code == 2


def test_missing_path_exits_2(in_tmp):
    assert run("check", "does-not-exist").exit_code == 2


def test_invalid_config_exits_2(in_tmp):
    write(in_tmp / "m" / "0001.sql", "SELECT 1;\n")
    write(in_tmp / ".migrationguard.yml", "fail_on: SEVERE\n")
    r = run("check", "m")
    assert r.exit_code == 2 and "CONFIG_ERROR" in r.output


def test_fail_on_option_overrides_config(in_tmp):
    write(in_tmp / "m" / "0001.sql", "ALTER TABLE users DROP COLUMN email;\n")
    write(in_tmp / ".migrationguard.yml", "fail_on: HIGH\n")
    assert run("check", "m").exit_code == 1
    assert run("check", "m", "--fail-on", "CRITICAL").exit_code == 0


def test_bad_suppression_exits_2(in_tmp):
    write(in_tmp / "m" / "0001.sql", "-- migration-guard: ignore MG001\nDROP TABLE a;\n")
    r = run("check", "m")
    assert r.exit_code == 2 and "SUPPRESSION_ERROR" in r.output


def test_ignore_paths_from_config(in_tmp):
    write(in_tmp / "migrations" / "legacy" / "0001.sql", "DROP TABLE a;\n")
    write(in_tmp / "migrations" / "0002.sql", "SELECT 1;\n")
    write(in_tmp / ".migrationguard.yml", 'ignore_paths: ["migrations/legacy/**"]\n')
    assert run("check", "migrations").exit_code == 0


def test_json_output_round_trips(in_tmp):
    write(in_tmp / "m" / "0001.sql", "SELECT 1;\nALTER TABLE payments DROP COLUMN card_number;\n")
    r = run("check", "m", "--format", "json", "--output", "report.json")
    assert r.exit_code == 1
    result = AnalysisResult.model_validate_json(r.output)
    assert result.schema_version == "1"
    assert result.summary.findings == 1 and result.exit_code == 1
    f = result.findings[0]
    assert (f.rule_id, f.table, f.object, f.line, f.statement_index) == (
        "MG003",
        "payments",
        "card_number",
        2,
        2,
    )
    assert json.loads((in_tmp / "report.json").read_text()) == json.loads(r.output)


def test_json_output_for_config_error(in_tmp):
    write(in_tmp / "m" / "0001.sql", "SELECT 1;\n")
    r = run("check", "m", "--config", "missing.yml", "--format", "json")
    assert r.exit_code == 2
    assert AnalysisResult.model_validate_json(r.output).errors[0].kind == "CONFIG_ERROR"


def test_github_format_and_step_summary(in_tmp, monkeypatch):
    summary = in_tmp / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    write(
        in_tmp / "m" / "0001.sql",
        "DROP TABLE payments;\nCREATE INDEX i ON t (c);\n",
    )
    r = run("check", "m", "--format", "github")
    assert r.exit_code == 1
    assert "::error file=m/0001.sql,line=1,title=MG001 CRITICAL%3A DROP_TABLE::" in r.output
    assert "::warning file=m/0001.sql,line=2," in r.output
    text = summary.read_text()
    assert "## MigrationGuard: BLOCKED" in text and "| blocking | MG001 |" in text


def test_example_folders(in_tmp):
    root = FIXTURES.parent.parent / "examples"
    shutil.copytree(root, in_tmp / "examples")
    assert run("check", "examples/safe_migrations").exit_code == 0
    assert run("check", "examples/unsafe_migrations").exit_code == 1
