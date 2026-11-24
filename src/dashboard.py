from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from src.config import MonitorConfig
from src.tracker import EvaluatedOffer


def generate_dashboard_html(
    history: Dict[str, Any],
    config: MonitorConfig,
    evaluated: List[EvaluatedOffer] | None = None,
    output_path: str | Path = "docs/index.html",
) -> Path:
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    routes: Dict[str, Any] = history.get("routes", {})
    last_run = history.get("last_run_utc") or datetime.now(timezone.utc).isoformat()
    queries = config.build_queries()

    rows: List[Dict[str, Any]] = []
    for q in queries:
        entry = routes.get(q.route_key, {})
        obs = entry.get("observations", [])
        latest_obs = obs[-1] if obs else None
        prev_obs = obs[-2] if len(obs) >= 2 else None

        latest_price = latest_obs["price_usd"] if latest_obs else None
        prev_price = prev_obs["price_usd"] if prev_obs else None
        lowest_ever = entry.get("lowest_ever_usd")
        airline = latest_obs.get("airline", "—") if latest_obs else "Pending first run"
        stops = latest_obs.get("stops", "—") if latest_obs else "—"

        change_pct = None
        if latest_price is not None and prev_price:
            change_pct = round(((latest_price - prev_price) / prev_price) * 100.0, 1)

        in_budget = latest_price is not None and latest_price <= config.target_max_price_usd
        is_drop = change_pct is not None and change_pct <= -config.drop_threshold_pct

        gf_url = (
            f"https://www.google.com/travel/flights?q=Flights%20to%20{q.destination}"
            f"%20from%20{q.origin}%20on%20{q.departure_date}%20through%20{q.return_date}%20business%20class"
        )

        rows.append(
            {
                "route": f"{q.origin} → {q.destination}",
                "route_key": q.route_key,
                "departure_date": q.departure_date,
                "return_date": q.return_date,
                "trip_length_days": q.trip_length_days,
                "airline": airline,
                "stops": stops,
                "latest_price": latest_price,
                "prev_price": prev_price,
                "lowest_ever": lowest_ever,
                "change_pct": change_pct,
                "in_budget": in_budget,
                "is_drop": is_drop,
                "history": [{"t": o["timestamp"][:10], "p": o["price_usd"]} for o in obs[-30:]],
                "preferred_offers": entry.get("latest_preferred_offers", []),
                "url": gf_url,
            }
        )

    priced_rows = [r for r in rows if r["latest_price"] is not None]
    best_price = min((r["latest_price"] for r in priced_rows), default=None)
    deals_count = sum(1 for r in priced_rows if r["in_budget"] or r["is_drop"])

    data_json = json.dumps(
        {
            "last_run_utc": last_run,
            "target_max_price_usd": config.target_max_price_usd,
            "drop_threshold_pct": config.drop_threshold_pct,
            "nonstop_only": config.nonstop_only,
            "preferred_airlines": config.preferred_airlines,
            "rows": rows,
        }
    )

    best_str = f"${best_price:,.0f}" if best_price is not None else "Pending"

    stop_label = "Nonstop only" if config.nonstop_only else (
        f"Up to {config.max_stops} stop(s)" if config.max_stops is not None else "Any stops"
    )

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>USA → Kenya Business Class Monitor (June 2027)</title>
  <style>
    :root {{
      --bg: #0b1120; --card: #111827; --border: #1f2937;
      --text: #f3f4f6; --muted: #9ca3af; --accent: #14b8a6;
      --good: #10b981; --warn: #f59e0b; --bad: #ef4444;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; padding: 24px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg); color: var(--text); line-height: 1.5;
    }}
    .container {{ max-width: 1100px; margin: 0 auto; }}
    h1 {{ margin: 0 0 4px; font-size: 24px; }}
    .sub {{ color: var(--muted); font-size: 13px; margin-bottom: 20px; }}
    .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; margin-bottom: 20px; }}
    .card {{
      background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 16px;
    }}
    .kpi-label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em; }}
    .kpi-val {{ font-size: 26px; font-weight: 700; margin-top: 4px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid var(--border); text-align: left; }}
    th {{ color: var(--muted); font-weight: 600; font-size: 12px; text-transform: uppercase; }}
    .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .badge {{
      display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; font-weight: 600;
    }}
    .badge-good {{ background: rgba(16,185,129,0.15); color: var(--good); }}
    .badge-warn {{ background: rgba(245,158,11,0.15); color: var(--warn); }}
    .badge-muted {{ background: rgba(156,163,175,0.15); color: var(--muted); }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    canvas {{ width: 100%; height: 220px; display: block; }}
  </style>
</head>
<body>
  <div class="container">
    <h1>USA → Kenya Business Class Price Monitor</h1>
    <div class="sub">June 2027 · {html.escape(stop_label)} · Last Updated: {html.escape(last_run)}</div>

    <div class="kpis">
      <div class="card"><div class="kpi-label">Active Queries</div><div class="kpi-val">{len(rows)} / day</div></div>
      <div class="card"><div class="kpi-label">Best Fare Found</div><div class="kpi-val">{best_str}</div></div>
      <div class="card"><div class="kpi-label">Target Budget</div><div class="kpi-val">&le; ${config.target_max_price_usd:,.0f}</div></div>
      <div class="card"><div class="kpi-label">Active Deals</div><div class="kpi-val">{deals_count}</div></div>
    </div>

    <div class="card" style="margin-bottom: 20px;">
      <div class="kpi-label" style="margin-bottom: 10px;">Price Trend (Last 30 Checks)</div>
      <canvas id="trendChart" height="220"></canvas>
    </div>

    <div class="card" style="overflow-x: auto; margin-bottom: 20px;">
      <div class="kpi-label" style="margin-bottom: 10px;">Cheapest Fares by Route &amp; Date</div>
      <table>
        <thead>
          <tr>
            <th>Route</th><th>Departure</th><th>Return</th><th class="num">Days</th>
            <th>Airline</th><th class="num">Latest</th><th class="num">Change</th>
            <th class="num">Lowest Ever</th><th>Status</th><th>Book</th>
          </tr>
        </thead>
        <tbody id="rowsBody"></tbody>
      </table>
    </div>

    <div class="card" id="prefCard" style="overflow-x: auto; display: none;">
      <div class="kpi-label" style="margin-bottom: 10px;">British Airways &amp; American Airlines Options</div>
      <table>
        <thead>
          <tr>
            <th>Route</th><th>Departure</th><th>Return</th><th class="num">Days</th>
            <th>Airline</th><th class="num">Stops</th><th class="num">Price</th><th>Book</th>
          </tr>
        </thead>
        <tbody id="prefBody"></tbody>
      </table>
    </div>
  </div>

  <script>
    const DATA = {data_json};
    const tbody = document.getElementById("rowsBody");
    const sorted = [...DATA.rows].sort((a, b) => (a.latest_price ?? 999999) - (b.latest_price ?? 999999));

    for (const r of sorted) {{
      const tr = document.createElement("tr");
      const price = r.latest_price !== null ? `$${{r.latest_price.toLocaleString()}}` : "Pending";
      const lowest = r.lowest_ever !== null ? `$${{r.lowest_ever.toLocaleString()}}` : "—";
      let changeStr = "—";
      if (r.change_pct !== null) {{
        changeStr = r.change_pct > 0 ? `+${{r.change_pct}}%` : `${{r.change_pct}}%`;
      }}
      let status = `<span class="badge badge-muted">Tracking</span>`;
      if (r.in_budget) status = `<span class="badge badge-good">In Budget</span>`;
      else if (r.is_drop) status = `<span class="badge badge-warn">25%+ Drop</span>`;

      tr.innerHTML = `
        <td><b>${{r.route}}</b></td>
        <td>${{r.departure_date}}</td>
        <td>${{r.return_date}}</td>
        <td class="num">${{r.trip_length_days}}</td>
        <td>${{r.airline}}</td>
        <td class="num"><b>${{price}}</b></td>
        <td class="num">${{changeStr}}</td>
        <td class="num">${{lowest}}</td>
        <td>${{status}}</td>
        <td><a href="${{r.url}}" target="_blank" rel="noopener">Google Flights</a></td>
      `;
      tbody.appendChild(tr);
    }}

    const prefBody = document.getElementById("prefBody");
    const prefRows = [];
    for (const r of DATA.rows) {{
      for (const po of (r.preferred_offers || [])) {{
        prefRows.push({{ ...r, po }});
      }}
    }}
    prefRows.sort((a, b) => a.po.price_usd - b.po.price_usd);
    if (prefRows.length > 0) {{
      document.getElementById("prefCard").style.display = "block";
      for (const item of prefRows) {{
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td><b>${{item.route}}</b></td>
          <td>${{item.departure_date}}</td>
          <td>${{item.return_date}}</td>
          <td class="num">${{item.trip_length_days}}</td>
          <td>${{item.po.airline}}</td>
          <td class="num">${{item.po.stops}}</td>
          <td class="num"><b>$${{item.po.price_usd.toLocaleString()}}</b></td>
          <td><a href="${{item.url}}" target="_blank" rel="noopener">Google Flights</a></td>
        `;
        prefBody.appendChild(tr);
      }}
    }}

    // Simple Canvas line chart
    const canvas = document.getElementById("trendChart");
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    canvas.width = canvas.clientWidth * dpr;
    canvas.height = 220 * dpr;
    ctx.scale(dpr, dpr);
    const W = canvas.clientWidth, H = 220, pad = 40;
    const allPts = DATA.rows.flatMap(r => r.history.map(h => h.p));
    if (allPts.length === 0) {{
      ctx.fillStyle = "#9ca3af";
      ctx.font = "13px sans-serif";
      ctx.fillText("No price history recorded yet. Run the GitHub Action to populate live prices.", pad, H / 2);
    }} else {{
      const minP = Math.min(...allPts, DATA.target_max_price_usd) * 0.92;
      const maxP = Math.max(...allPts, DATA.target_max_price_usd) * 1.05;
      const yFor = p => H - pad - ((p - minP) / (maxP - minP || 1)) * (H - 2 * pad);

      // Target budget dashed line
      ctx.strokeStyle = "#10b981";
      ctx.setLineDash([5, 5]);
      ctx.beginPath();
      ctx.moveTo(pad, yFor(DATA.target_max_price_usd));
      ctx.lineTo(W - pad, yFor(DATA.target_max_price_usd));
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = "#10b981";
      ctx.font = "11px sans-serif";
      ctx.fillText(`Target $${{DATA.target_max_price_usd.toLocaleString()}}`, pad + 4, yFor(DATA.target_max_price_usd) - 6);

      const colors = ["#14b8a6", "#3b82f6", "#f59e0b", "#a855f7"];
      DATA.rows.forEach((r, idx) => {{
        if (!r.history.length) return;
        ctx.strokeStyle = colors[idx % colors.length];
        ctx.lineWidth = 2;
        ctx.beginPath();
        r.history.forEach((pt, i) => {{
          const x = pad + (i / Math.max(1, r.history.length - 1)) * (W - 2 * pad);
          const y = yFor(pt.p);
          if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }});
        ctx.stroke();
      }});
    }}
  </script>
</body>
</html>
"""
    out_path.write_text(page, encoding="utf-8")
    return out_path
