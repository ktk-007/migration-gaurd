"""Line numbers must be exact; they become inline annotations on the PR."""

from __future__ import annotations

import pytest

from conftest import FIXTURES
from migration_guard.parser import ParseFailure, parse_file, parse_text


def lines(sql: str) -> list[int]:
    return [s.line for s in parse_text(sql).statements]


def test_multiple_statements_get_index_and_line():
    parsed = parse_text("SELECT 1;\nSELECT 2;\n\nSELECT 3;")
    assert [s.index for s in parsed.statements] == [1, 2, 3]
    assert [s.line for s in parsed.statements] == [1, 2, 4]


def test_leading_comments_and_blank_lines_are_skipped():
    sql = "-- header\n\n/* block\n comment */\n\nDROP TABLE x;"
    assert lines(sql) == [6]


def test_whitespace_after_previous_statement_is_skipped():
    # pglast can point at the newline after the previous ';'.
    assert lines("DROP TABLE a;\nCREATE INDEX i ON t (c);") == [1, 2]


def test_crlf_line_endings():
    assert lines("SELECT 1;\r\n-- c\r\n\r\nDROP TABLE x;\r\n") == [1, 4]


def test_multibyte_characters_before_statement():
    # 'é' and the emoji are several bytes each in UTF-8; lines must still be right.
    sql = "SELECT 'café ☕';\nSELECT 'ünïcödé';\nDROP TABLE x;"
    assert lines(sql) == [1, 2, 3]


def test_nested_block_comment():
    assert lines("/* a /* b */ c */\nSELECT 1;") == [2]


def test_comment_only_file_has_no_statements():
    assert parse_text("-- nothing here\n").statements == []


def test_parse_failure_line_after_multibyte_characters():
    with pytest.raises(ParseFailure) as exc:
        parse_text("SELECT '☕☕☕☕';\nSELECT 'é';\nDROP TABEL x;")
    assert exc.value.line == 3


def test_parse_failure_has_line():
    with pytest.raises(ParseFailure) as exc:
        parse_text("SELECT 1;\n\nDROP TABEL x;")
    assert exc.value.line == 3
    assert "TABEL" in exc.value.message


def test_hand_checked_fixture():
    parsed = parse_file(FIXTURES / "unsafe" / "line_numbers.sql")
    assert [s.line for s in parsed.statements] == [5, 9, 12]


def test_utf8_bom_is_ignored(tmp_path):
    f = tmp_path / "bom.sql"
    f.write_bytes(b"\xef\xbb\xbfDROP TABLE x;")
    assert [s.line for s in parse_file(f).statements] == [1]
