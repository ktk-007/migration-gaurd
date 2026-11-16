"""Config, policy thresholds, overrides and suppression."""

from __future__ import annotations

import pytest

from conftest import findings_for
from migration_guard.config import Config, ConfigError, load_config
from migration_guard.models import Severity
from migration_guard.suppressions import SuppressionError

# One finding of each severity: CRITICAL, HIGH, MEDIUM.
MIXED = "DROP TABLE a;\nALTER TABLE b DROP COLUMN c;\nCREATE INDEX i ON d (e);"


@pytest.mark.parametrize(
    ("fail_on", "blocking"),
    [
        (Severity.LOW, {"MG001", "MG003", "MG006"}),
        (Severity.MEDIUM, {"MG001", "MG003", "MG006"}),
        (Severity.HIGH, {"MG001", "MG003"}),
        (Severity.CRITICAL, {"MG001"}),
    ],
)
def test_fail_on_threshold(fail_on, blocking):
    found = findings_for(MIXED, Config(fail_on=fail_on))
    assert {f.rule_id for f in found if f.blocking} == blocking
    assert len(found) == 3  # non-blocking findings are still reported


def test_severity_override():
    cfg = Config.model_validate({"rules": {"MG006": {"severity": "HIGH"}}})
    (f,) = findings_for("CREATE INDEX i ON t (c);", cfg)
    assert f.severity is Severity.HIGH and f.blocking


def test_rule_can_be_disabled():
    cfg = Config.model_validate({"rules": {"MG001": {"enabled": False}}})
    assert findings_for("DROP TABLE a;", cfg) == []


def test_ignore_paths_globs():
    cfg = Config(ignore_paths=["migrations/legacy/**", "*.tmp.sql"])
    assert cfg.is_ignored("migrations/legacy/0001.sql")
    assert cfg.is_ignored("migrations/legacy/old/0002.sql")
    assert cfg.is_ignored("x.tmp.sql")
    assert not cfg.is_ignored("migrations/0003.sql")


def test_defaults_without_config_file(in_tmp):
    cfg = load_config(None)
    assert cfg.fail_on is Severity.HIGH and cfg.rules == {}


def test_loads_yaml(in_tmp):
    (in_tmp / ".migrationguard.yml").write_text(
        "version: 1\ndialect: postgres\nfail_on: CRITICAL\nrules:\n  MG010:\n    enabled: false\n"
    )
    cfg = load_config(None)
    assert cfg.fail_on is Severity.CRITICAL
    assert not cfg.is_enabled("MG010")


@pytest.mark.parametrize(
    "yaml_text",
    [
        "fail_no: HIGH\n",  # typo in a key
        "fail_on: SEVERE\n",  # unknown severity
        "dialect: mysql\n",  # unsupported dialect
        "version: 2\n",  # unsupported version
        "rules:\n  MG999:\n    enabled: false\n",  # unknown rule id
        "rules:\n  MG001:\n    enabeld: false\n",  # typo inside a rule
        "- just\n- a list\n",  # wrong top-level type
        "fail_on: [unclosed\n",  # broken YAML
    ],
)
def test_invalid_config_is_an_error(in_tmp, yaml_text):
    (in_tmp / "bad.yml").write_text(yaml_text)
    with pytest.raises(ConfigError):
        load_config(in_tmp / "bad.yml")


def test_missing_explicit_config_is_an_error(in_tmp):
    with pytest.raises(ConfigError):
        load_config(in_tmp / "nope.yml")


def test_suppression_with_reason():
    sql = (
        '-- migration-guard: ignore MG003 reason="column unused since v2.3"\n'
        "ALTER TABLE users DROP COLUMN legacy;"
    )
    (f,) = findings_for(sql)
    assert f.suppressed and not f.blocking
    assert f.suppression_reason == "column unused since v2.3"


def test_suppression_only_covers_named_rule():
    sql = (
        '-- migration-guard: ignore MG003 reason="ok"\n'
        "ALTER TABLE t DROP COLUMN a, ALTER COLUMN b TYPE text;"
    )
    by_rule = {f.rule_id: f for f in findings_for(sql)}
    assert by_rule["MG003"].suppressed
    assert not by_rule["MG004"].suppressed and by_rule["MG004"].blocking


def test_suppression_several_ids_and_stacked_comments():
    sql = (
        '-- migration-guard: ignore MG003, MG004 reason="planned cleanup"\n'
        "-- ordinary comment in between\n"
        "ALTER TABLE t DROP COLUMN a, ALTER COLUMN b TYPE text;"
    )
    assert all(f.suppressed for f in findings_for(sql))


def test_blank_line_breaks_suppression():
    sql = '-- migration-guard: ignore MG001 reason="x"\n\nDROP TABLE a;'
    (f,) = findings_for(sql)
    assert not f.suppressed and f.blocking


def test_suppression_applies_to_next_statement_only():
    sql = '-- migration-guard: ignore MG001 reason="x"\nDROP TABLE a;\nDROP TABLE b;'
    assert [f.suppressed for f in findings_for(sql)] == [True, False]


@pytest.mark.parametrize(
    "directive",
    [
        "-- migration-guard: ignore MG003",  # no reason
        '-- migration-guard: ignore MG003 reason=""',  # empty reason
        '-- migration-guard: ignore MG999 reason="x"',  # unknown rule
        "-- migration-guard: skip MG003",  # malformed
    ],
)
def test_bad_suppression_is_an_error(directive):
    with pytest.raises(SuppressionError):
        findings_for(f"{directive}\nALTER TABLE users DROP COLUMN legacy;")
