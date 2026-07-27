"""Core data model: the normalized ``Finding`` contract and report envelope.

See DESIGN.md §4. Implemented in issue #2.
"""

from enum import StrEnum

from pydantic import BaseModel


class Category(StrEnum):
    VALIDATION = "validation"
    CORE = "core"
    BEST_PRACTICE = "best-practice"
    EXTENSION = "extension"


class Confidence(StrEnum):
    NORMATIVE = "normative"
    HEURISTIC = "heuristic"


class Reference(BaseModel):
    title: str
    href: str
    version: str | None = None


class Finding(BaseModel):
    source: str
    category: Category
    confidence: Confidence
    message: str
    json_path: str | None = None
    references: list[Reference] = []


class UsageSummary(BaseModel):
    tokens: int
    cost: float
    model: str


class ValidationReport(BaseModel):
    item_id: str
    source_uri: str
    generated_on: str
    gated: bool
    findings: list[Finding]
    usage: UsageSummary | None
