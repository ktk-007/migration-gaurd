# MigrationGuard design notes

## Pipeline

1. **Scanner** (`scanner.py`) chooses files. With paths, it collects every
   `.sql` file under them. With `--changed-since REF`, it runs
   `git diff --name-only -z --diff-filter=ACMR REF...HEAD` from the repository
   root and keeps `.sql` files under the given paths.
   - Three dots: compare against the merge base, so commits that landed on the
     base branch after we branched are not counted as ours.
   - `ACMR`: added, copied, modified **and renamed**. Leaving out renames would
     let a migration that is renamed and edited skip the check (failing open).
   - A missing ref is exit 2 with a hint about `fetch-depth: 0`.
2. **Parser** (`parser.py`) calls `pglast.parse_sql`. Each `RawStmt` gives the
   AST node and `stmt_location`. In pglast 8 this is a character offset into the
   Python string (libpg_query works in bytes; pglast converts). Tests with
   multi-byte characters, CRLF line endings, a BOM, nested block comments and
   leading comments guard this, so a behaviour change in a future pglast release
   would fail CI instead of producing wrong annotations. As a defensive step the
   parser skips whitespace and comments at the reported offset.
3. **Suppression reader** (`suppressions.py`) validates every
   `-- migration-guard:` directive in the file up front, then for each statement
   collects directives from the contiguous comment block directly above it.
4. **Rule engine** (`rules/`). `Rule` subclasses declare `id`, `title`,
   `severity`, `category` and the pglast node types they handle, and yield `Hit`
   objects. `@register` adds them to the registry.
5. **Policy** (`analyzer.py` + `config.py`). Per-rule `enabled` and `severity`
   overrides, then `blocking = not suppressed and severity >= fail_on`.
6. **Reporters** render the same `AnalysisResult`.
7. **Exit code**: errors → 2, else blocking findings → 1, else 0.

## Why these choices

| Decision | Alternative | Reason |
|---|---|---|
| pglast | regex, SQLGlot | It is PostgreSQL's own parser, so anything Postgres accepts parses identically, and Postgres-specific flags are first-class fields. SQLGlot makes sense if more dialects are added. |
| Fail closed | warn and continue | A gate that passes on input it cannot read is not a gate. |
| Severity vs `fail_on` | per-rule block flag | Teams adopt gradually: start with `fail_on: CRITICAL`, then tighten. |
| Strict config (`extra="forbid"`) | ignore unknown keys | `fail_no: HIGH` must not silently fall back to defaults. |
| Changed files only in CI | whole folder | Old applied migrations must not block unrelated PRs; also keeps the check fast. |
| JSON = Pydantic model | hand-built dict | One source of truth for the schema; consumers can validate with the same model. |

## Adding a rule

1. Write a `Rule` subclass in the matching module under `rules/`, decorated with
   `@register`.
2. Add positive and negative cases to `tests/test_rules.py`.

Nothing else changes. MG008-MG010 were added this way.

## Rollout at scale

Ship as a reusable workflow, start with a lenient `fail_on` (or warn-only by
reading the JSON), track false-positive reports and suppression reasons, then
tighten the threshold team by team.
