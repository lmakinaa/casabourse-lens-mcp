"""
Corporate-action domain.

Exposes the canonical event types, the point-in-time SQLite store,
the reconciler, and the pure back-adjustment function. Scraper /
ingestion-side code lives in the top-level `ingestion` package —
everything here is read-path + pure numerics.
"""

from .events import (
    CorporateAction,
    EventType,
    Confidence,
    EventStatus,
    CandidateObservation,
)
from .store import CorporateActionStore
from .reconciler import Reconciler, ReconciliationPolicy
from .validator import ValidationError, validate_observation
from .adjuster import AdjustedBar, AdjustmentReport, back_adjust
from .service import CorporateActionService

__all__ = [
    "CorporateAction",
    "EventType",
    "Confidence",
    "EventStatus",
    "CandidateObservation",
    "CorporateActionStore",
    "Reconciler",
    "ReconciliationPolicy",
    "ValidationError",
    "validate_observation",
    "AdjustedBar",
    "AdjustmentReport",
    "back_adjust",
    "CorporateActionService",
]
