"""Execution context handed to every tool handler."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..corporate_actions import CorporateActionService
from ..providers import DataProvider
from ..technical_analysis import TechnicalAnalysis


@dataclass(frozen=True)
class ToolContext:
    provider: DataProvider
    tech_analysis: TechnicalAnalysis
    corporate_actions: Optional[CorporateActionService] = None
