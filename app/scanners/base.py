from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class OwaspCategory(str, Enum):
    """OWASP Top 10 for LLM Applications (2025)."""

    LLM01_PROMPT_INJECTION = "LLM01: Prompt Injection"
    LLM02_SENSITIVE_INFO_DISCLOSURE = "LLM02: Sensitive Information Disclosure"
    LLM03_SUPPLY_CHAIN = "LLM03: Supply Chain"
    LLM04_DATA_MODEL_POISONING = "LLM04: Data and Model Poisoning"
    LLM05_IMPROPER_OUTPUT_HANDLING = "LLM05: Improper Output Handling"
    LLM06_EXCESSIVE_AGENCY = "LLM06: Excessive Agency"
    LLM07_SYSTEM_PROMPT_LEAKAGE = "LLM07: System Prompt Leakage"
    LLM08_VECTOR_WEAKNESSES = "LLM08: Vector and Embedding Weaknesses"
    LLM09_MISINFORMATION = "LLM09: Misinformation"
    LLM10_UNBOUNDED_CONSUMPTION = "LLM10: Unbounded Consumption"


@dataclass
class Violation:
    rule: str
    category: OwaspCategory
    detail: str
    snippet: str | None = None


@dataclass
class ScanResult:
    layer: str
    safe: bool
    sanitized_text: str
    violations: list[Violation] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def blocked(self) -> bool:
        return not self.safe

    def primary_category(self) -> OwaspCategory | None:
        return self.violations[0].category if self.violations else None
