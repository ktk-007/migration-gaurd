"""--changed-since, tested against a real temporary git repository."""

from __future__ import annotations

import subprocess

import pytest
from typer.testing import CliRunner

from migration_guard.cli import app
from migration_guard.scanner import ScanError, changed_sql_files, collect_sql_files

pytestmark = pytest.mark.skipif(
    subprocess.run(["git", "--version"], capture_output=True).returncode != 0,
    reason="git not available",
)


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(in_tmp):
    git(in_tmp, "init", "-q", "-b", "main")
    git(in_tmp, "config", "user.email", "t@example.com")
    git(in_tmp, "config", "user.name", "Test")
    git(in_tmp, "config", "commit.gpgsign", "false")
    mig = in_tmp / "migrations"
    mig.mkdir()
    (mig / "0001_old.sql").write_text("DROP TABLE already_reviewed;\n")
    (mig / "0002_to_rename.sql").write_text("SELECT 1;\n")
    (in_tmp / "notes.sql").write_text("SELECT 1;\n")
    git(in_tmp, "add", ".")
    git(in_tmp, "commit", "-q", "-m", "base")
    git(in_tmp, "checkout", "-q", "-b", "feature")
    return in_tmp


def names(paths):
    return [p.name for p in paths]


def test_only_changed_files_are_returned(repo):
    (repo / "migrations" / "0003_new.sql").write_text("ALTER TABLE u DROP COLUMN e;\n")
    (repo / "migrations" / "README.md").write_text("not sql\n")
    (repo / "notes.sql").write_text("SELECT 2;\n")  # changed, but outside migrations/
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "feature")
    assert names(changed_sql_files("main", [repo / "migrations"])) == ["0003_new.sql"]


def test_renamed_and_edited_file_is_included(repo):
    git(repo, "mv", "migrations/0002_to_rename.sql", "migrations/0002_renamed.sql")
    (repo / "migrations" / "0002_renamed.sql").write_text("SELECT 1;\nTRUNCATE users;\n")
    git(repo, "commit", "-q", "-am", "rename")
    assert names(changed_sql_files("main", [repo / "migrations"])) == ["0002_renamed.sql"]


def test_deleted_file_is_not_included(repo):
    git(repo, "rm", "-q", "migrations/0001_old.sql")
    git(repo, "commit", "-q", "-m", "delete")
    assert changed_sql_files("main", [repo / "migrations"]) == []


def test_unknown_ref_is_an_error(repo):
    with pytest.raises(ScanError) as exc:
        changed_sql_files("origin/does-not-exist", [repo / "migrations"])
    assert "fetch-depth" in exc.value.message


def test_cli_changed_since_ignores_old_risky_files(repo):
    (repo / "migrations" / "0003_new.sql").write_text("ALTER TABLE u ADD COLUMN x int;\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "safe change")
    runner = CliRunner()
    # A full scan fails on the old DROP TABLE...
    assert runner.invoke(app, ["check", "migrations"]).exit_code == 1
    # ...but the PR only touched a safe file, so the PR check passes.
    r = runner.invoke(app, ["check", "migrations", "--changed-since", "main"])
    assert r.exit_code == 0, r.output
    assert "Files: 1" in r.output


def test_collect_finds_sql_recursively(in_tmp):
    (in_tmp / "a" / "b").mkdir(parents=True)
    (in_tmp / "a" / "1.sql").write_text("")
    (in_tmp / "a" / "b" / "2.SQL").write_text("")
    (in_tmp / "a" / "b" / "x.txt").write_text("")
    assert names(collect_sql_files([in_tmp / "a"])) == ["1.sql", "2.SQL"]
