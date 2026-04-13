"""
Ingestion pipeline for corporate actions.

Runs OUT OF PROCESS from the MCP server. Scrapers emit
CandidateObservation rows; the pipeline validates, dedupes, and
upserts into the SQLite event log; the reconciler rebuilds the
materialized view. The MCP server only reads.

This package is deliberately separate from `trading_tools` — read
and write paths must not share modules so we can scale ingestion
independently (a nightly cron, a long-running daemon, or a one-off
backfill) without touching the tool runtime.
"""

from .pipeline import IngestionPipeline, IngestionResult

__all__ = ["IngestionPipeline", "IngestionResult"]
