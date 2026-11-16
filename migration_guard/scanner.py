"""Find the .sql files to analyse: everything under the given paths, or only
files added, copied, modified or renamed since a git ref."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


class ScanError(Exception):
    """Bad path or git problem. Treated as a tool failure (exit 2)."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


def display_path(path: Path) -> str:
    """Path relative to the current directory with forward slashes, for reports and CI."""
    try:
        return Path(os.path.relpath(path.resolve(), Path.cwd())).as_posix()
    except ValueError:  # different drive on Windows
        return path.resolve().as_posix()


def collect_sql_files(paths: list[Path]) -> list[Path]:
    files: set[Path] = set()
    for p in paths:
        if p.is_file():
            if p.suffix.lower() == ".sql":
                files.add(p.resolve())
        elif p.is_dir():
            files.update(
                f.resolve() for f in p.rglob("*") if f.is_file() and f.suffix.lower() == ".sql"
            )
        else:
            raise ScanError("PATH_ERROR", f"Path does not exist: {p}")
    return sorted(files)


def _git(args: list[str], cwd: Path | None = None) -> str:
    try:
        proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise ScanError("GIT_ERROR", "git is not installed or not on PATH") from exc
    if proc.returncode != 0:
        raise ScanError("GIT_ERROR", proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout


def changed_sql_files(ref: str, paths: list[Path]) -> list[Path]:
    """SQL files under ``paths`` that changed between ``ref`` and HEAD.

    Uses the three-dot range (``ref...HEAD``) so only changes made on this branch
    count, not changes that landed on the base branch since we branched.
    ``--diff-filter=ACMR`` includes renamed files: a migration that is renamed
    *and* edited must still be checked, otherwise we would fail open.
    """
    for p in paths:
        if not p.exists():
            raise ScanError("PATH_ERROR", f"Path does not exist: {p}")

    top = Path(_git(["rev-parse", "--show-toplevel"]).strip())
    try:
        _git(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], cwd=top)
    except ScanError as exc:
        raise ScanError(
            "GIT_ERROR",
            f"Git ref '{ref}' not found. In CI, check out with fetch-depth: 0 so the base "
            "branch is available.",
        ) from exc

    out = _git(["diff", "--name-only", "-z", "--diff-filter=ACMR", f"{ref}...HEAD"], cwd=top)
    roots = [p.resolve() for p in paths]
    result = []
    for name in filter(None, out.split("\0")):
        f = (top / name).resolve()
        if f.suffix.lower() != ".sql" or not f.is_file():
            continue
        if any(f == r or r in f.parents for r in roots):
            result.append(f)
    return sorted(result)
