"""Machine-readable report.

The output is exactly ``AnalysisResult.model_dump_json()``, so the schema is the
Pydantic model in models.py and ``AnalysisResult.model_validate_json`` reads it
back. ``schema_version`` changes only when a field is removed or changes meaning.
"""

from __future__ import annotations

from migration_guard.models import AnalysisResult


def render_json(result: AnalysisResult) -> str:
    return result.model_dump_json(indent=2) + "\n"
