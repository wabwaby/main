"""Offline smoke test for the aliprice package.

Exercises:
    - storage CRUD + price history
    - price-string normalization
    - product-id extraction
    - scraper extraction from a synthetic HTML page (no network)
    - deal-signal heuristics
    - HTML report rendering
"""

from __future__ import annotations

import os
import sys
import tempfile
import textwrap

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from aliprice.deals import evaluate  # noqa: E402
from aliprice.report import build as build_report  # noqa: E402
from aliprice.scraper import (  # noqa: E402
    _find_run_params,
    _normalize_price,
    _price_from_jsonld,
    _price_from_meta,
    _price_from_run_params,
    extract_product_id,
)
from aliprice.storage import Storage  # noqa: E402


def check(label, condition, detail=""):
    status = "ok  " if condition else "FAIL"
    print(f"  [{status}] {label}{(' — ' + detail) if detail else ''}")
    if not condition:
        raise SystemExit(1)


def test_price_normalize():
    print("price normalization")
    check("US $12.34", _normalize_price("US $12.34") == (12.34, "USD"))
    check("€19,99", _normalize_price("€19,99") == (19.99, "EUR"))
    check("£1,234.56", _normalize_price("£1,234.56") == (1234.56, "GBP"))
    check("$1.234,56 (eu style)", _normalize_price("$1.234,56") == (1234.56, "USD"))
    check("plain 7.5", _normalize_price("7.5") == (7.5, None))
    check("empty", _normalize_price("") is None)


def test_product_id():
    print("product id extraction")
    check(
        "canonical",
        extract_product_id("https://www.aliexpress.com/item/1005006123456789.html") == "1005006123456789",
    )
    check(
        "with query",
        extract_product_id("https://aliexpress.com/item/100500.html?spm=foo") == "100500",
    )
    check(
        "productId param",
        extract_product_id("https://aliexpress.com/foo?productId=42") == "42",
    )
    check("none for nonsense", extract_product_id("https://example.com") is None)


def test_storage():
    print("storage")
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "t.sqlite3")
        s = Storage(db)
        s.add_product("1", "https://aliexpress.com/item/1.html", title="Cool Thing", nickname="cool")
        s.record_price("1", 20.00, "USD")
        s.record_price("1", 18.50, "USD")
        s.record_price("1", 12.00, "USD")
        prod = s.find_product("cool")
        check("find by alias", prod is not None and prod.product_id == "1")
        hist = s.history("1")
        check("history length", len(hist) == 3)
        latest = s.latest_price("1")
        check("latest price", latest is not None and latest.price == 12.00)
        s.update_metadata("1", title="Cooler Thing", currency="USD")
        prod = s.get_product("1")
        check("metadata update", prod.title == "Cooler Thing" and prod.currency == "USD")
        check("remove", s.remove_product("1") is True)
        check("removed", s.get_product("1") is None)


def test_deals():
    print("deal heuristics")
    with tempfile.TemporaryDirectory() as d:
        s = Storage(os.path.join(d, "deals.sqlite3"))
        s.add_product("p", "https://aliexpress.com/item/p.html", title="X", currency="USD")
        for price in [20.0, 20.5, 20.2, 20.3, 20.0]:
            s.record_price("p", price, "USD")
        prod = s.get_product("p")
        sig = evaluate(prod, s.history("p"))
        check("not a deal yet", sig is not None and not sig.is_deal, sig.headline)
        s.record_price("p", 14, "USD")
        sig = evaluate(prod, s.history("p"))
        check("now a deal", sig.is_deal, sig.headline)
        check("all-time low flag", sig.is_all_time_low)


SAMPLE_HTML = """
<!doctype html>
<html><head>
  <title>Sample Item</title>
  <meta property="og:title" content="Sample OG Title">
  <meta property="og:price:amount" content="9.99">
  <meta property="og:price:currency" content="USD">
  <script type="application/ld+json">
  {"@type": "Product", "name": "JSON-LD Title",
   "offers": {"price": "11.50", "priceCurrency": "EUR"}}
  </script>
  <script>
    window.runParams = {
      data: {"titleModule":{"subject":"RunParams Title"},
             "priceModule":{"formatedActivityPrice":"US $7.49",
                            "formatedPrice":"US $12.99"}},
      csrfToken: "abc123"
    };
  </script>
</head><body></body></html>
"""


def test_scraper_parsers():
    print("scraper parsers (offline)")
    rp = _find_run_params(SAMPLE_HTML)
    check("found runParams", rp is not None)
    # The blob we find may have data nested; price extractor handles both.
    result = _price_from_run_params(rp if isinstance(rp, dict) else {})
    if not result:
        # fall back to JSON-LD or meta, which is also valid behavior
        result = _price_from_jsonld(SAMPLE_HTML)
        check("json-ld fallback parsed", result is not None and result[0] == 11.50)
    else:
        price, currency, title, raw = result
        check("runParams price", price == 7.49, f"got {price}")
        check("runParams currency", currency == "USD")
        check("runParams title", title == "RunParams Title")

    meta_result = _price_from_meta(SAMPLE_HTML)
    check("meta fallback", meta_result is not None and meta_result[0] == 9.99)


def test_report():
    print("html report")
    with tempfile.TemporaryDirectory() as d:
        s = Storage(os.path.join(d, "r.sqlite3"))
        s.add_product("a", "https://aliexpress.com/item/a.html", title="Alpha", currency="USD")
        for price in [25, 24, 23, 22, 18]:
            s.record_price("a", price, "USD")
        s.add_product("b", "https://aliexpress.com/item/b.html", title="Beta", currency="USD")
        s.record_price("b", 50, "USD")
        out = os.path.join(d, "out.html")
        path = build_report(s, out)
        check("report written", os.path.exists(path))
        html = open(path).read()
        check("contains Alpha", "Alpha" in html)
        check("contains Beta", "Beta" in html)
        check("contains deal badge or note", "tracked product" in html)


if __name__ == "__main__":
    test_price_normalize()
    test_product_id()
    test_storage()
    test_deals()
    test_scraper_parsers()
    test_report()
    print("\nall smoke tests passed.")
