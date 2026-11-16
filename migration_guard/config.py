"""Load and validate .migrationguard.yml.

The models forbid unknown keys, so a typo such as ``fail_no: HIGH`` is an error
instead of being silently ignored. Every config problem raises ConfigError,
which the CLI turns into exit code 2 (fail closed).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from migration_guard.models import Severity
from migration_guard.rules import rule_ids

DEFAULT_CONFIG_NAME = ".migrationguard.yml"


class ConfigError(Exception):
    pass


class RuleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    severity: Severity | None = None


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    dialect: Literal["postgres"] = "postgres"
    fail_on: Severity = Severity.HIGH
    ignore_paths: list[str] = Field(default_factory=list)
    rules: dict[str, RuleConfig] = Field(default_factory=dict)

    @field_validator("rules")
    @classmethod
    def _known_rules_only(cls, value: dict[str, RuleConfig]) -> dict[str, RuleConfig]:
        unknown = sorted(set(value) - rule_ids())
        if unknown:
            raise ValueError(f"unknown rule id(s): {', '.join(unknown)}")
        return value

    def is_enabled(self, rule_id: str) -> bool:
        rc = self.rules.get(rule_id)
        return rc.enabled if rc else True

    def severity_for(self, rule_id: str, default: Severity) -> Severity:
        rc = self.rules.get(rule_id)
        return rc.severity if rc and rc.severity else default

    def is_ignored(self, rel_path: str) -> bool:
        return any(_glob_to_regex(p).fullmatch(rel_path) for p in self.ignore_paths)


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate a glob with ``**`` support into a regex ('**' crosses directories)."""
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out))


def load_config(path: Path | None) -> Config:
    """Load ``path`` if given; otherwise ./.migrationguard.yml if present; otherwise defaults."""
    if path is None:
        default = Path(DEFAULT_CONFIG_NAME)
        if not default.is_file():
            return Config()
        path = default
    elif not path.is_file():
        raise ConfigError(f"Config file not found: {path}")

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"Could not read {path}: {exc}") from exc

    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: the top level must be a mapping of keys to values")

    try:
        return Config.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or '(root)'}: {err['msg']}"
            for err in exc.errors()
        )
        raise ConfigError(f"Invalid config {path}: {problems}") from exc
