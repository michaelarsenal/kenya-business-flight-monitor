from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import MonitorConfig
from src.providers import FlightOffer


@dataclass
class EvaluatedOffer:
    offer: FlightOffer
    previous_price_usd: Optional[float]
    rolling_avg_usd: Optional[float]
    lowest_ever_usd: float
    drop_vs_prev_pct: Optional[float]
    drop_vs_avg_pct: Optional[float]
    in_target_range: bool
    is_significant_drop: bool
    should_alert: bool
    alert_reasons: List[str]


def load_history(path: str | Path) -> Dict[str, Any]:
    history_path = Path(path)
    if not history_path.exists():
        return {"routes": {}, "last_run_utc": None}
    with history_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_history(path: str | Path, history: Dict[str, Any]) -> None:
    history_path = Path(path)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, sort_keys=True)


def evaluate_and_update(
    offers: List[FlightOffer],
    history: Dict[str, Any],
    config: MonitorConfig,
    now_utc: Optional[datetime] = None,
) -> List[EvaluatedOffer]:
    timestamp = (now_utc or datetime.now(timezone.utc)).isoformat()
    routes: Dict[str, Any] = history.setdefault("routes", {})
    evaluated: List[EvaluatedOffer] = []

    for offer in offers:
        key = offer.route_key
        entry = routes.setdefault(
            key,
            {
                "origin": offer.origin,
                "destination": offer.destination,
                "departure_date": offer.departure_date,
                "return_date": offer.return_date,
                "trip_length_days": offer.trip_length_days,
                "observations": [],
                "lowest_ever_usd": None,
                "last_alerted_price_usd": None,
            },
        )

        obs: List[Dict[str, Any]] = entry.get("observations", [])
        previous_price: Optional[float] = obs[-1]["price_usd"] if obs else None
        rolling_avg: Optional[float] = (
            round(sum(o["price_usd"] for o in obs) / len(obs), 2) if obs else None
        )

        prev_lowest = entry.get("lowest_ever_usd")
        lowest_ever = (
            min(float(prev_lowest), offer.price_usd)
            if prev_lowest is not None
            else offer.price_usd
        )

        drop_vs_prev_pct: Optional[float] = None
        if previous_price and previous_price > 0:
            drop_vs_prev_pct = round(
                ((previous_price - offer.price_usd) / previous_price) * 100.0, 1
            )

        drop_vs_avg_pct: Optional[float] = None
        if rolling_avg and rolling_avg > 0:
            drop_vs_avg_pct = round(
                ((rolling_avg - offer.price_usd) / rolling_avg) * 100.0, 1
            )

        in_target_range = offer.price_usd <= config.target_max_price_usd
        is_drop_prev = (
            drop_vs_prev_pct is not None and drop_vs_prev_pct >= config.drop_threshold_pct
        )
        is_drop_avg = (
            drop_vs_avg_pct is not None and drop_vs_avg_pct >= config.drop_threshold_pct
        )
        is_significant_drop = is_drop_prev or is_drop_avg

        alert_reasons: List[str] = []
        if in_target_range:
            alert_reasons.append(
                f"Within target budget (<= ${config.target_max_price_usd:,.0f})"
            )
        if is_drop_prev and drop_vs_prev_pct is not None:
            alert_reasons.append(
                f"{drop_vs_prev_pct:.1f}% below previous check (${previous_price:,.0f})"
            )
        elif is_drop_avg and drop_vs_avg_pct is not None:
            alert_reasons.append(
                f"{drop_vs_avg_pct:.1f}% below historical average (${rolling_avg:,.0f})"
            )

        last_alerted = entry.get("last_alerted_price_usd")
        should_alert = False
        if alert_reasons:
            if last_alerted is None:
                should_alert = True
            elif offer.price_usd <= float(last_alerted) - config.min_realert_drop_usd:
                should_alert = True

        # Append today's observation (keep last 90 observations)
        obs.append(
            {
                "timestamp": timestamp,
                "price_usd": offer.price_usd,
                "airline": offer.airline,
                "stops": offer.stops,
                "provider": offer.provider,
            }
        )
        entry["observations"] = obs[-90:]
        entry["lowest_ever_usd"] = lowest_ever
        if should_alert:
            entry["last_alerted_price_usd"] = offer.price_usd

        evaluated.append(
            EvaluatedOffer(
                offer=offer,
                previous_price_usd=previous_price,
                rolling_avg_usd=rolling_avg,
                lowest_ever_usd=lowest_ever,
                drop_vs_prev_pct=drop_vs_prev_pct,
                drop_vs_avg_pct=drop_vs_avg_pct,
                in_target_range=in_target_range,
                is_significant_drop=is_significant_drop,
                should_alert=should_alert,
                alert_reasons=alert_reasons,
            )
        )

    history["last_run_utc"] = timestamp
    return evaluated
