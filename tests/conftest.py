from __future__ import annotations

from pathlib import Path

import pytest

from migration_guard.analyzer import analyze_parsed
from migration_guard.config import Config
from migration_guard.models import Finding
from migration_guard.parser import parse_text

FIXTURES = Path(__file__).parent / "fixtures"


def findings_for(sql: str, config: Config | None = None) -> list[Finding]:
    """Analyse an SQL string with the given (or default) config."""
    return analyze_parsed(parse_text(sql, "test.sql"), config or Config())


def rule_ids_for(sql: str, config: Config | None = None) -> list[str]:
    return [f.rule_id for f in findings_for(sql, config)]


@pytest.fixture
def in_tmp(tmp_path, monkeypatch):
    """Run a test with the current directory set to an empty temporary folder."""
    monkeypatch.chdir(tmp_path)
    return tmp_path
