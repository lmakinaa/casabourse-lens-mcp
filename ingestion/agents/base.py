"""
BaseAgent — protocol for source-specific scrapers.

Agents transform an external source into a stream of
CandidateObservation rows. They do NOT persist, do NOT reconcile, and
do NOT pre-validate — the ingestion pipeline owns all of that.

ManualAgent intentionally does NOT inherit from this: its interface is
`from_dict(entries)` not `run(since, until)`, since its input arrives
via CLI/JSON, not a date window. That asymmetry is by design — forcing
ManualAgent into a date-window shape would be a leaky abstraction.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import ClassVar, Iterator

from trading_tools.corporate_actions import CandidateObservation, Confidence


class BaseAgent(ABC):
    """
    Protocol for scheduled, source-backed ingestion agents.

    Subclasses MUST set SOURCE and CONFIDENCE at class level — the
    reconciler's precedence ranking keys off these exact strings.
    """

    SOURCE: ClassVar[str]
    CONFIDENCE: ClassVar[Confidence]

    @abstractmethod
    def run(self, since: date, until: date) -> Iterator[CandidateObservation]:
        """Yield observations whose ex_date falls in [since, until]."""
