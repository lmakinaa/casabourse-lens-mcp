"""
Source-specific ingestion agents.

Each agent is a callable returning an Iterable[CandidateObservation].
Agents MUST NOT write to the store directly — they hand their output
to the pipeline, which owns validation + persistence.

v1 ships only the ManualAgent (CLI-driven). Bourse de Casablanca and
AMMC agents live on their own follow-up branches.
"""

from .manual import ManualAgent

__all__ = ["ManualAgent"]
