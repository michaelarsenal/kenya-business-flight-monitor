from __future__ import annotations

import argparse
import sys
import time
from typing import List

from src.config import load_config
from src.notifier import dispatch_notifications
from src.providers import FlightOffer, get_provider
from src.tracker import evaluate_and_update, load_history, save_history


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monitor Business Class flight prices from USA to Kenya (June 2027)."
    )
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument(
        "--history", default="data/price_history.json", help="Path to price history JSON"
    )
    parser.add_argument(
        "--report", default="data/latest_report.md", help="Path to latest markdown report"
    )
    parser.add_argument(
        "--provider",
        default=None,
        choices=["serpapi", "searchapi", "amadeus", "mock"],
        help="Override flight API provider (default: auto-detect from env, else mock)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not send SMTP emails; print report to stdout",
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config)
    provider = get_provider(args.provider)
    queries = config.build_queries()
    print(f"Running monitor with provider={provider.name}, queries={len(queries)}")

    offers: List[FlightOffer] = []
    errors: List[str] = []

    for idx, q in enumerate(queries):
        try:
            offer = provider.search_lowest_offer(q)
            if offer is not None:
                offers.append(offer)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{q.route_key}: {exc}")

        if idx < len(queries) - 1 and config.request_delay_seconds > 0 and provider.name != "mock":
            time.sleep(config.request_delay_seconds)

    history = load_history(args.history)
    evaluated = evaluate_and_update(offers, history, config)
    save_history(args.history, history)

    dispatch_notifications(
        evaluated=evaluated,
        config=config,
        errors=errors,
        report_path=args.report,
        dry_run=args.dry_run,
    )

    if not offers and errors:
        print("All queries failed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
