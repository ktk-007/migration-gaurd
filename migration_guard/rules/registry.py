"""Central rule registry.

Rules register themselves with the ``@register`` decorator. The analyzer only
ever asks the registry for rules, so adding a rule never touches the analyzer.
"""

from __future__ import annotations

from migration_guard.rules.base import Rule

_RULES: dict[str, Rule] = {}


def register(cls: type[Rule]) -> type[Rule]:
    if cls.id in _RULES:
        raise ValueError(f"Duplicate rule id {cls.id}")
    _RULES[cls.id] = cls()
    return cls


def all_rules() -> list[Rule]:
    _load()
    return [_RULES[k] for k in sorted(_RULES)]


def get_rule(rule_id: str) -> Rule | None:
    _load()
    return _RULES.get(rule_id)


def rule_ids() -> set[str]:
    _load()
    return set(_RULES)


def _load() -> None:
    # Importing the modules runs their @register decorators.
    from migration_guard.rules import data, destructive, locking  # noqa: F401
