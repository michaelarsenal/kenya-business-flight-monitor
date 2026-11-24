from datetime import datetime, timezone

from src.config import MonitorConfig, load_config
from src.notifier import build_summary_markdown
from src.providers import FlightOffer
from src.tracker import evaluate_and_update


def _make_config() -> MonitorConfig:
    return MonitorConfig(
        origins=["JFK"],
        destinations=["NBO"],
        departure_dates=["2027-06-10"],
        trip_lengths_days=[11],
        cabin="BUSINESS",
        currency="USD",
        adults=1,
        target_max_price_usd=3500.0,
        drop_threshold_pct=25.0,
        min_realert_drop_usd=50.0,
        send_daily_summary=True,
        send_instant_alerts=True,
        request_delay_seconds=0.0,
    )


def _make_offer(price: float) -> FlightOffer:
    return FlightOffer(
        origin="JFK",
        destination="NBO",
        departure_date="2027-06-10",
        return_date="2027-06-21",
        trip_length_days=11,
        price_usd=price,
        airline="Qatar Airways",
        stops=1,
        provider="mock",
    )


def test_target_price_alert_and_deduplication() -> None:
    cfg = _make_config()
    history: dict = {"routes": {}}

    # First check at $3,400 -> triggers target budget alert
    res1 = evaluate_and_update([_make_offer(3400.0)], history, cfg, datetime.now(timezone.utc))
    assert len(res1) == 1
    assert res1[0].in_target_range is True
    assert res1[0].should_alert is True

    # Second check at $3,380 (only $20 cheaper, < $50 min_realert_drop_usd) -> deduplicated
    res2 = evaluate_and_update([_make_offer(3380.0)], history, cfg, datetime.now(timezone.utc))
    assert res2[0].in_target_range is True
    assert res2[0].should_alert is False

    # Third check at $3,300 ($100 cheaper than last alerted $3,400) -> re-alerts
    res3 = evaluate_and_update([_make_offer(3300.0)], history, cfg, datetime.now(timezone.utc))
    assert res3[0].should_alert is True


def test_25_percent_drop_alert_above_target_budget() -> None:
    cfg = _make_config()
    history: dict = {"routes": {}}

    # Day 1: $5,200 (above $3,500 target, no drop yet)
    res1 = evaluate_and_update([_make_offer(5200.0)], history, cfg, datetime.now(timezone.utc))
    assert res1[0].should_alert is False

    # Day 2: $3,800 (~26.9% drop vs $5,200, even though > $3,500) -> triggers 25% drop alert
    res2 = evaluate_and_update([_make_offer(3800.0)], history, cfg, datetime.now(timezone.utc))
    assert res2[0].in_target_range is False
    assert res2[0].is_significant_drop is True
    assert res2[0].drop_vs_prev_pct == 26.9
    assert res2[0].should_alert is True


def test_config_and_summary_markdown() -> None:
    cfg = load_config("config.yaml")
    queries = cfg.build_queries()
    assert len(queries) == len(cfg.origins) * len(cfg.destinations) * len(cfg.departure_dates) * len(cfg.trip_lengths_days)
    assert all(10 <= q.trip_length_days <= 18 for q in queries)

    history: dict = {"routes": {}}
    evaluated = evaluate_and_update([_make_offer(3450.0)], history, cfg)
    md = build_summary_markdown(evaluated, cfg, errors=[])
    assert "JFK->NBO" in md
    assert "$3,450" in md
