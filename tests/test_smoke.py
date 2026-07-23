"""Smoke tests: the package and its module layout import cleanly.

This validates the scaffolding from issue #1 — every stub module in the
``DESIGN.md`` §13 layout is importable. The optional ``api`` extra
(``stac_validator_plus.api``) is intentionally excluded so the core package
does not depend on FastAPI being installed.
"""

import importlib

import pytest

MODULES = [
    "stac_validator_plus",
    "stac_validator_plus.cli",
    "stac_validator_plus.config",
    "stac_validator_plus.models",
    "stac_validator_plus.pipeline",
    "stac_validator_plus.backend",
    "stac_validator_plus.backend.loader",
    "stac_validator_plus.backend.gate",
    "stac_validator_plus.backend.checks",
    "stac_validator_plus.backend.checks.schema",
    "stac_validator_plus.backend.checks.lint",
    "stac_validator_plus.backend.plugins",
    "stac_validator_plus.backend.plugins.extensions",
    "stac_validator_plus.backend.claude",
    "stac_validator_plus.backend.claude.runner",
    "stac_validator_plus.backend.claude.orchestrator",
    "stac_validator_plus.backend.claude.prompts",
    "stac_validator_plus.report",
    "stac_validator_plus.report.render",
]


@pytest.mark.parametrize("module", MODULES)
def test_module_imports(module: str) -> None:
    importlib.import_module(module)
