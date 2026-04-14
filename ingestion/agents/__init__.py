"""
Source-specific ingestion agents.

Each agent produces an Iterable[CandidateObservation]. Agents MUST NOT
write to the store directly — they hand their output to the pipeline,
which owns validation + persistence + reconciliation.

Phase 1 agents:
  - ManualAgent       — CLI / JSON-driven; interface is from_dict()
  - BourseCasaAgent   — BC JSON:API; interface is run(since, until)

ManualAgent intentionally does NOT inherit from BaseAgent — its input
shape is different. See base.py for rationale.
"""

from .base import BaseAgent
from .bourse_casa import BourseCasaAgent, load_issuer_map
from .manual import ManualAgent

__all__ = ["BaseAgent", "BourseCasaAgent", "ManualAgent", "load_issuer_map"]
