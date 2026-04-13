"""
Command-line entry point for manual ingestion.

Examples:
  # Single event
  python -m ingestion record \\
    --db data/corporate_actions.sqlite \\
    --symbol ATW --type dividend \\
    --ex-date 2025-05-12 --amount 16.5 \\
    --operator alice

  # Bulk from JSON
  python -m ingestion record-file \\
    --db data/corporate_actions.sqlite \\
    --file events.json --operator alice

  # Inspect
  python -m ingestion show --db data/corporate_actions.sqlite --symbol ATW
  python -m ingestion coverage --db data/corporate_actions.sqlite --symbol ATW
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

from trading_tools.corporate_actions import (
    CorporateActionStore,
    EventType,
    Reconciler,
)

from .agents import ManualAgent
from .pipeline import IngestionPipeline


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ingestion", description=__doc__)
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/corporate_actions.sqlite"),
        help="Path to the SQLite event store (default: data/corporate_actions.sqlite)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    rec = sub.add_parser("record", help="Record one manual observation")
    rec.add_argument("--symbol", required=True)
    rec.add_argument(
        "--type",
        dest="event_type",
        required=True,
        choices=[e.value for e in EventType],
    )
    rec.add_argument("--ex-date", required=True, help="ISO date, e.g. 2025-05-12")
    rec.add_argument("--amount", type=float, help="Dividend amount per share")
    rec.add_argument("--ratio", type=float, help="Split ratio new:old (e.g. 2.0 for 2:1)")
    rec.add_argument("--subscription-price", type=float)
    rec.add_argument("--currency", default="MAD")
    rec.add_argument("--operator", default="unknown")
    rec.add_argument("--source-url")

    recf = sub.add_parser("record-file", help="Bulk record observations from JSON array")
    recf.add_argument("--file", type=Path, required=True)
    recf.add_argument("--operator", default="unknown")

    show = sub.add_parser("show", help="Show reconciled events for a symbol")
    show.add_argument("--symbol", required=True)
    show.add_argument("--include-pending", action="store_true")

    cov = sub.add_parser("coverage", help="Show source coverage for a symbol")
    cov.add_argument("--symbol", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    args = _build_parser().parse_args(argv)
    store = CorporateActionStore(args.db)

    try:
        if args.command == "record":
            return _cmd_record(store, args)
        if args.command == "record-file":
            return _cmd_record_file(store, args)
        if args.command == "show":
            return _cmd_show(store, args)
        if args.command == "coverage":
            return _cmd_coverage(store, args)
    finally:
        store.close()

    return 2


def _cmd_record(store: CorporateActionStore, args: argparse.Namespace) -> int:
    entry: Dict[str, Any] = {
        "symbol": args.symbol,
        "event_type": args.event_type,
        "ex_date": args.ex_date,
    }
    if args.amount is not None:
        entry["amount"] = args.amount
    if args.ratio is not None:
        entry["ratio"] = args.ratio
    if args.subscription_price is not None:
        entry["subscription_price"] = args.subscription_price
    if args.currency:
        entry["currency"] = args.currency
    if args.source_url:
        entry["source_url"] = args.source_url

    agent = ManualAgent(operator=args.operator)
    observations = agent.from_dict([entry])

    pipeline = IngestionPipeline(store)
    result = pipeline.ingest(observations)

    print(
        json.dumps(
            {
                "accepted": result.accepted,
                "rejected": result.rejected,
                "warnings": result.warnings,
                "reconciled_symbols": result.reconciled_symbols,
            },
            indent=2,
        )
    )
    return 0 if not result.rejected else 1


def _cmd_record_file(store: CorporateActionStore, args: argparse.Namespace) -> int:
    with args.file.open("r", encoding="utf-8") as fh:
        entries = json.load(fh)
    if not isinstance(entries, list):
        print("error: input JSON must be a top-level array", file=sys.stderr)
        return 2

    agent = ManualAgent(operator=args.operator)
    observations = agent.from_dict(entries)

    pipeline = IngestionPipeline(store)
    result = pipeline.ingest(observations)

    print(
        json.dumps(
            {
                "accepted": result.accepted,
                "rejected": result.rejected,
                "warnings": result.warnings,
                "reconciled_symbols": result.reconciled_symbols,
            },
            indent=2,
        )
    )
    return 0 if not result.rejected else 1


def _cmd_show(store: CorporateActionStore, args: argparse.Namespace) -> int:
    Reconciler(store).reconcile_symbol(args.symbol.strip().upper())
    events = store.get_events(args.symbol.strip().upper(), include_pending=args.include_pending)
    print(json.dumps([e.to_dict() for e in events], indent=2))
    return 0


def _cmd_coverage(store: CorporateActionStore, args: argparse.Namespace) -> int:
    print(json.dumps(store.coverage(args.symbol.strip().upper()), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
