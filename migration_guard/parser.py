"""Turn a .sql file into a list of statements with correct line numbers.

pglast wraps libpg_query, the parser from PostgreSQL itself. libpg_query
reports byte offsets, but pglast 8 converts them to *character* offsets into the
Python string (verified with multi-byte characters; tests guard this, so a
future pglast change would be caught).

As a defensive step we also skip any whitespace or comments at the reported
offset, so the line number is always the line of the statement's first token.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pglast import parse_sql
from pglast.parser import ParseError


class ParseFailure(Exception):
    """The file is not valid PostgreSQL. Callers must treat this as a tool failure."""

    def __init__(self, message: str, line: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.line = line


@dataclass(frozen=True)
class Statement:
    index: int  # 1-based position in the file
    line: int  # 1-based line of the first token
    node: Any  # the pglast AST node (e.g. DropStmt)


@dataclass(frozen=True)
class ParsedFile:
    path: str
    text: str
    statements: list[Statement]


def read_sql(path: Path) -> str:
    """Read a file as UTF-8, dropping a BOM if an editor added one."""
    return path.read_bytes().decode("utf-8-sig")


def _skip_trivia(text: str, pos: int) -> int:
    """Move ``pos`` forward past whitespace, ``--`` comments and ``/* */`` comments."""
    n = len(text)
    while pos < n:
        if text[pos].isspace():
            pos += 1
        elif text.startswith("--", pos):
            end = text.find("\n", pos)
            pos = n if end == -1 else end + 1
        elif text.startswith("/*", pos):
            # PostgreSQL block comments nest.
            depth, pos = 1, pos + 2
            while pos < n and depth:
                if text.startswith("/*", pos):
                    depth, pos = depth + 1, pos + 2
                elif text.startswith("*/", pos):
                    depth, pos = depth - 1, pos + 2
                else:
                    pos += 1
        else:
            break
    return pos


def line_of_offset(text: str, offset: int) -> int:
    """1-based line number of a character offset. Works for LF and CRLF files."""
    return text.count("\n", 0, offset) + 1


def parse_text(text: str, path: str = "<string>") -> ParsedFile:
    """Parse SQL text. Raises ParseFailure if PostgreSQL would reject it."""
    try:
        raw_statements = parse_sql(text)
    except ParseError as exc:
        message = exc.args[0] if exc.args else str(exc)
        line = None
        if len(exc.args) > 1 and isinstance(exc.args[1], int):
            line = line_of_offset(text, exc.args[1])
        raise ParseFailure(f"PostgreSQL could not parse this file: {message}", line) from exc

    statements = []
    for i, raw in enumerate(raw_statements or (), start=1):
        start = _skip_trivia(text, raw.stmt_location or 0)
        statements.append(Statement(index=i, line=line_of_offset(text, start), node=raw.stmt))
    return ParsedFile(path=path, text=text, statements=statements)


def parse_file(path: Path, display_path: str | None = None) -> ParsedFile:
    return parse_text(read_sql(path), display_path or path.as_posix())
