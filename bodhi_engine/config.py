"""
Lightweight project-level config loaded from .bodhi/config.yaml.

This is distinct from .bodhi/bodhi.yaml (which describes the *project* —
name, languages, distribution model). config.yaml holds *tool behavior*
overrides: which lint rules to relax, which symbols to whitelist, etc.

Kept intentionally small — adding a knob here means committing to support
it across validator, score, and CI. Don't grow this without thinking twice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class BodhiConfig:
    # Fully-qualified ClassName.methodName entries that are allowed to have
    # multiple tagged implementations. Use sparingly — Builder/fluent APIs
    # and legitimate Java overload sites only.
    allow_overload: set[str] = field(default_factory=set)


def load_config(project_root: Path) -> BodhiConfig:
    """Load .bodhi/config.yaml if present. Missing file → empty config."""
    config_file = project_root / ".bodhi" / "config.yaml"
    if not config_file.is_file():
        return BodhiConfig()

    try:
        with open(config_file) as f:
            data = yaml.safe_load(f) or {}
    except (yaml.YAMLError, OSError):
        return BodhiConfig()

    allow = data.get("allow_overload") or []
    return BodhiConfig(allow_overload=set(allow))
