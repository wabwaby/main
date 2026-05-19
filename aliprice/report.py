"""Generate a self-contained local HTML dashboard of tracked products."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Iterable

from jinja2 import Template

from .deals import DealSignal
from .storage import PricePoint, Storage


TEMPLATE = Template(
    """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>AliPrice Tracker</title>
<style>
  :root {
    color-scheme: light dark;
    --bg: #0f1115;
    --card: #181b22;
    --border: #2a2f3a;
    --text: #e6e8ee;
    --muted: #9aa3b2;
    --accent: #4ade80;
    --warn: #f59e0b;
    --bad: #ef4444;
    --link: #60a5fa;
  }
  @media (prefers-color-scheme: light) {
    :root {
      --bg: #f6f7fb;
      --card: #ffffff;
      --border: #e4e7ee;
      --text: #1a1d23;
      --muted: #5b6473;
      --accent: #16a34a;
      --warn: #b45309;
      --bad: #b91c1c;
      --link: #2563eb;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.45;
    padding: 32px 24px 64px;
  }
  h1 { margin: 0 0 4px 0; font-size: 28px; }
  .subtitle { color: var(--muted); margin-bottom: 28px; font-size: 14px; }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: 16px;
  }
  .card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px 18px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .card.deal { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent) inset; }
  .title {
    font-weight: 600;
    font-size: 15px;
    line-height: 1.3;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .title a { color: var(--text); text-decoration: none; }
  .title a:hover { color: var(--link); }
  .price {
    font-size: 24px;
    font-weight: 700;
    letter-spacing: -0.01em;
  }
  .price .currency { color: var(--muted); font-size: 14px; font-weight: 500; margin-right: 4px; }
  .badge {
    display: inline-block;
    font-size: 12px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 999px;
    background: rgba(74, 222, 128, 0.15);
    color: var(--accent);
    border: 1px solid var(--accent);
    align-self: flex-start;
  }
  .badge.warn { background: rgba(245, 158, 11, 0.1); color: var(--warn); border-color: var(--warn); }
  .badge.muted { background: transparent; color: var(--muted); border-color: var(--border); }
  .stats {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 6px;
    font-size: 12px;
    color: var(--muted);
    margin-top: 4px;
  }
  .stats div strong { display: block; color: var(--text); font-size: 13px; font-weight: 600; }
  .spark { width: 100%; height: 56px; margin-top: 6px; }
  .footer { color: var(--muted); font-size: 12px; margin-top: 6px; }
  .empty {
    padding: 48px;
    text-align: center;
    color: var(--muted);
    background: var(--card);
    border: 1px dashed var(--border);
    border-radius: 12px;
  }
  code {
    background: rgba(255,255,255,0.06);
    padding: 1px 6px;
    border-radius: 4px;
    font-size: 12px;
  }
</style>
</head>
<body>
  <h1>AliPrice Tracker</h1>
  <div class="subtitle">
    {{ deals_count }} deal{{ '' if deals_count == 1 else 's' }} ·
    {{ products_count }} tracked product{{ '' if products_count == 1 else 's' }} ·
    generated {{ generated_at }}
  </div>

  {% if not entries %}
    <div class="empty">
      <p>No products yet.</p>
      <p>Add one with: <code>python -m aliprice add &lt;aliexpress-url&gt;</code></p>
    </div>
  {% else %}
    <div class="grid">
      {% for e in entries %}
      <div class="card{% if e.signal and e.signal.is_deal %} deal{% endif %}">
        <div class="title">
          <a href="{{ e.product.url }}" target="_blank" rel="noopener">
            {{ e.product.title or e.product.nickname or e.product.product_id }}
          </a>
        </div>

        {% if e.signal %}
          <div class="price">
            <span class="currency">{{ e.signal.currency or '' }}</span>{{ '%.2f' % e.signal.current_price }}
          </div>
          {% if e.signal.is_deal %}
            <span class="badge">{{ e.signal.headline }}</span>
          {% elif e.signal.samples < 2 %}
            <span class="badge muted">just started tracking</span>
          {% else %}
            <span class="badge muted">{{ e.signal.headline }}</span>
          {% endif %}

          <svg class="spark" viewBox="0 0 100 30" preserveAspectRatio="none">
            <polyline fill="none" stroke="currentColor" stroke-width="1.5"
              points="{{ e.spark_points }}" />
          </svg>

          <div class="stats">
            <div><strong>{{ '%.2f' % e.signal.lowest_price }}</strong>lowest</div>
            <div><strong>{{ '%.2f' % e.signal.average_price }}</strong>average</div>
            <div><strong>{{ e.signal.samples }}</strong>samples</div>
          </div>
        {% else %}
          <div class="price">—</div>
          <span class="badge muted">no price data yet</span>
        {% endif %}

        <div class="footer">
          ID {{ e.product.product_id }}
          {% if e.product.nickname %} · alias <code>{{ e.product.nickname }}</code>{% endif %}
          {% if e.product.last_checked %} · last checked {{ e.product.last_checked }}{% endif %}
        </div>
      </div>
      {% endfor %}
    </div>
  {% endif %}
</body>
</html>
"""
)


def _spark_points(history: list[PricePoint]) -> str:
    if not history:
        return ""
    prices = [p.price for p in history]
    if len(prices) == 1:
        prices = prices * 2
    lo, hi = min(prices), max(prices)
    span = hi - lo or 1.0
    width = 100.0
    height = 30.0
    pts = []
    n = len(prices)
    for i, price in enumerate(prices):
        x = (i / (n - 1)) * width if n > 1 else 0
        y = height - ((price - lo) / span) * height
        pts.append(f"{x:.1f},{y:.1f}")
    return " ".join(pts)


def build(storage: Storage, output_path: str) -> str:
    """Render an HTML report to ``output_path`` and return its path."""
    products = storage.list_products()
    entries = []
    deals_count = 0
    from .deals import evaluate  # avoid circular at import time

    for product in products:
        history = storage.history(product.product_id)
        signal = evaluate(product, history)
        if signal and signal.is_deal:
            deals_count += 1
        entries.append(
            {
                "product": product,
                "signal": signal,
                "spark_points": _spark_points(history),
            }
        )

    # Sort: deals first, then by drop_vs_average_pct desc, then by title.
    def sort_key(e):
        s = e["signal"]
        is_deal = bool(s and s.is_deal)
        drop = s.drop_vs_average_pct if s else -1e9
        return (not is_deal, -drop, (e["product"].title or "").lower())

    entries.sort(key=sort_key)

    html = TEMPLATE.render(
        entries=entries,
        deals_count=deals_count,
        products_count=len(products),
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )

    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    return output_path
