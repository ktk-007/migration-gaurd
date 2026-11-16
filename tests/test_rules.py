"""Every rule has positive cases (must flag) and negative cases (must not flag)."""

from __future__ import annotations

import pytest

from conftest import findings_for, rule_ids_for
from migration_guard.models import Severity

POSITIVE = [
    ("MG001", "DROP TABLE payments;"),
    ("MG001", "DROP TABLE IF EXISTS billing.payments CASCADE;"),
    ("MG002", "TRUNCATE payments;"),
    ("MG002", "TRUNCATE TABLE a, b RESTART IDENTITY;"),
    ("MG003", "ALTER TABLE users DROP COLUMN email;"),
    ("MG003", "ALTER TABLE users DROP COLUMN IF EXISTS email;"),
    ("MG004", "ALTER TABLE users ALTER COLUMN age TYPE bigint;"),
    ("MG004", "ALTER TABLE users ALTER COLUMN age SET DATA TYPE text USING age::text;"),
    ("MG005", "ALTER TABLE users ADD COLUMN plan text NOT NULL;"),
    ("MG006", "CREATE INDEX idx_users_email ON users (email);"),
    ("MG006", "CREATE UNIQUE INDEX idx_users_email ON users (email);"),
    ("MG007", "DELETE FROM sessions;"),
    ("MG007", "UPDATE users SET active = false;"),
    ("MG008", "ALTER TABLE orders ADD CONSTRAINT fk FOREIGN KEY (user_id) REFERENCES users(id);"),
    ("MG008", "ALTER TABLE orders ADD CONSTRAINT positive CHECK (amount > 0);"),
    ("MG009", "ALTER TABLE users ALTER COLUMN email SET NOT NULL;"),
    ("MG010", "ALTER TABLE users RENAME COLUMN email TO email_address;"),
    ("MG010", "ALTER TABLE users RENAME TO accounts;"),
]

NEGATIVE = [
    "CREATE TABLE users (id bigint PRIMARY KEY, email text NOT NULL);",
    "ALTER TABLE users ADD COLUMN last_login timestamptz;",
    "ALTER TABLE users ADD COLUMN plan text NOT NULL DEFAULT 'free';",
    "ALTER TABLE users ADD COLUMN id2 bigint GENERATED ALWAYS AS IDENTITY;",
    "CREATE INDEX CONCURRENTLY idx_users_email ON users (email);",
    "DELETE FROM sessions WHERE expires_at < now();",
    "UPDATE users SET active = false WHERE last_login < '2020-01-01';",
    "SELECT * FROM users;",
    "DROP INDEX CONCURRENTLY idx_old;",
    "DROP VIEW old_report;",
    "ALTER TABLE orders ADD CONSTRAINT fk FOREIGN KEY (user_id) REFERENCES users(id) NOT VALID;",
    "ALTER TABLE orders ADD CONSTRAINT positive CHECK (amount > 0) NOT VALID;",
    "ALTER TABLE orders VALIDATE CONSTRAINT fk_user;",
    "ALTER TABLE users ALTER COLUMN email DROP NOT NULL;",
    "ALTER INDEX idx_a RENAME TO idx_b;",
    "INSERT INTO plans (name) VALUES ('free');",
]


@pytest.mark.parametrize(("rule_id", "sql"), POSITIVE)
def test_rule_flags_risky_sql(rule_id, sql):
    assert rule_id in rule_ids_for(sql)


@pytest.mark.parametrize("sql", NEGATIVE)
def test_safe_sql_is_not_flagged(sql):
    assert rule_ids_for(sql) == []


def test_every_rule_has_positive_case():
    from migration_guard.rules import rule_ids

    assert {r for r, _ in POSITIVE} == rule_ids()


@pytest.mark.parametrize(
    "sql",
    [
        "-- DROP TABLE payments;\nSELECT 1;",
        "/* TRUNCATE users; */ SELECT 1;",
        "SELECT 'DROP TABLE payments';",
        "INSERT INTO audit (note) VALUES ('ALTER TABLE users DROP COLUMN email');",
        "SELECT $$DELETE FROM users$$;",
    ],
)
def test_keywords_in_comments_and_strings_are_ignored(sql):
    assert findings_for(sql) == []


def test_drop_several_tables_reports_each():
    found = findings_for("DROP TABLE a, public.b;")
    assert [f.table for f in found] == ["a", "public.b"]


def test_alter_table_with_several_actions_reports_each():
    sql = "ALTER TABLE users DROP COLUMN a, ALTER COLUMN b TYPE text, ADD COLUMN c int NOT NULL;"
    assert sorted(rule_ids_for(sql)) == ["MG003", "MG004", "MG005"]


def test_finding_details():
    (f,) = findings_for("SELECT 1;\nALTER TABLE billing.payments DROP COLUMN card_number;")
    assert f.rule_id == "MG003"
    assert f.severity is Severity.HIGH
    assert f.table == "billing.payments"
    assert f.object == "card_number"
    assert f.statement_index == 2
    assert f.line == 2
    assert f.blocking is True
    assert "expand-and-contract" in f.recommendation


def test_index_recommendation_mentions_transaction_block():
    (f,) = findings_for("CREATE INDEX i ON t (c);")
    assert "transaction block" in f.recommendation


def test_unique_constraint_is_not_mg008():
    # UNIQUE cannot be NOT VALID in PostgreSQL, so MG008 must not suggest it.
    assert "MG008" not in rule_ids_for("ALTER TABLE t ADD CONSTRAINT u UNIQUE (a);")
