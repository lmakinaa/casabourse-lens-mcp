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

from .agents import BourseCasaAgent, ManualAgent, load_issuer_map
from .http import PoliteClient
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

    bc = sub.add_parser(
        "scrape-bourse",
        help="Scrape Bourse de Casablanca dividends into the store",
    )
    bc.add_argument("--since", required=True, help="ISO date (inclusive)")
    bc.add_argument("--until", help="ISO date (inclusive); defaults to today")
    bc.add_argument(
        "--dry-run",
        action="store_true",
        help="Print candidate observations as JSON; skip DB writes",
    )
    bc.add_argument(
        "--user-agent",
        default="casabourse-lens/0.1 (+https://github.com/ijaija/casabourse-lens)",
    )
    bc.add_argument(
        "--min-interval",
        type=float,
        default=1.0,
        help="Seconds between requests to a given host (default 1.0)",
    )

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
        if args.command == "scrape-bourse":
            return _cmd_scrape_bourse(store, args)
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


def _cmd_scrape_bourse(store: CorporateActionStore, args: argparse.Namespace) -> int:
    try:
        since = date.fromisoformat(args.since)
    except ValueError:
        print(f"error: invalid --since date: {args.since!r}", file=sys.stderr)
        return 2

    until_raw = args.until or date.today().isoformat()
    try:
        until = date.fromisoformat(until_raw)
    except ValueError:
        print(f"error: invalid --until date: {until_raw!r}", file=sys.stderr)
        return 2

    if since > until:
        print("error: --since must be <= --until", file=sys.stderr)
        return 2

    with PoliteClient(user_agent=args.user_agent, min_interval=args.min_interval) as client:
        agent = BourseCasaAgent(client, issuer_map=load_issuer_map())
        observations = list(agent.run(since=since, until=until))

    if args.dry_run:
        print(
            json.dumps(
                [
                    {
                        "symbol": obs.symbol,
                        "event_type": obs.event_type.value,
                        "ex_date": obs.ex_date.isoformat(),
                        "payload": obs.payload,
                        "source": obs.source,
                        "confidence": obs.confidence.value,
                        "source_url": obs.source_url,
                        "source_ref": obs.source_ref,
                        "observed_at": obs.observed_at,
                    }
                    for obs in observations
                ],
                indent=2,
            )
        )
        return 0

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


if __name__ == "__main__":
    raise SystemExit(main())
