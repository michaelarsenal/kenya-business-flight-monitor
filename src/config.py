from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

import yaml


@dataclass(frozen=True)
class SearchQuery:
    origin: str
    destination: str
    departure_date: str
    return_date: str
    trip_length_days: int
    cabin: str = "BUSINESS"
    currency: str = "USD"
    adults: int = 1
    nonstop_only: bool = False
    max_stops: Optional[int] = None

    @property
    def route_key(self) -> str:
        return f"{self.origin}-{self.destination}-{self.departure_date}-{self.return_date}"


@dataclass
class MonitorConfig:
    origins: List[str]
    destinations: List[str]
    departure_dates: List[str]
    trip_lengths_days: List[int]
    cabin: str
    currency: str
    adults: int
    nonstop_only: bool
    max_stops: Optional[int]
    target_max_price_usd: float
    drop_threshold_pct: float
    min_realert_drop_usd: float
    send_daily_summary: bool
    send_instant_alerts: bool
    request_delay_seconds: float

    def build_queries(self) -> List[SearchQuery]:
        queries: List[SearchQuery] = []
        for origin in self.origins:
            for dest in self.destinations:
                for dep_str in self.departure_dates:
                    dep_dt = datetime.strptime(dep_str, "%Y-%m-%d")
                    for length in self.trip_lengths_days:
                        ret_dt = dep_dt + timedelta(days=length)
                        queries.append(
                            SearchQuery(
                                origin=origin.strip().upper(),
                                destination=dest.strip().upper(),
                                departure_date=dep_str,
                                return_date=ret_dt.strftime("%Y-%m-%d"),
                                trip_length_days=length,
                                cabin=self.cabin.strip().upper(),
                                currency=self.currency.strip().upper(),
                                adults=self.adults,
                                nonstop_only=self.nonstop_only,
                                max_stops=self.max_stops,
                            )
                        )
        return queries


def load_config(path: str | Path = "config.yaml") -> MonitorConfig:
    cfg_path = Path(path)
    with cfg_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    raw_max_stops = raw.get("max_stops")
    max_stops = int(raw_max_stops) if raw_max_stops is not None else None

    return MonitorConfig(
        origins=list(raw["origins"]),
        destinations=list(raw["destinations"]),
        departure_dates=list(raw["departure_dates"]),
        trip_lengths_days=[int(x) for x in raw["trip_lengths_days"]],
        cabin=str(raw.get("cabin", "BUSINESS")),
        currency=str(raw.get("currency", "USD")),
        adults=int(raw.get("adults", 1)),
        nonstop_only=bool(raw.get("nonstop_only", False)),
        max_stops=max_stops,
        target_max_price_usd=float(raw.get("target_max_price_usd", 3500.0)),
        drop_threshold_pct=float(raw.get("drop_threshold_pct", 25.0)),
        min_realert_drop_usd=float(raw.get("min_realert_drop_usd", 50.0)),
        send_daily_summary=bool(raw.get("send_daily_summary", True)),
        send_instant_alerts=bool(raw.get("send_instant_alerts", True)),
        request_delay_seconds=float(raw.get("request_delay_seconds", 0.25)),
    )
