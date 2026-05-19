"""AliExpress product page scraper.

Extracts the current selling price and title from an AliExpress product page.

Strategy (most stable first):

1. Parse the embedded JSON in ``window.runParams`` (the SKU module exposes
   ``priceModule.formatedActivityPrice`` / ``formatedPrice`` and the
   ``titleModule``).
2. Fall back to JSON-LD ``application/ld+json`` blocks if present.
3. Fall back to OpenGraph / meta tags for the title and to regex-based
   extraction of numeric prices as a last resort.

AliExpress changes its markup occasionally; if a fetch fails to extract a
price you can pass ``--debug`` to dump the HTML and inspect it.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


CURRENCY_SYMBOLS = {
    "$": "USD",
    "US $": "USD",
    "US$": "USD",
    "€": "EUR",
    "£": "GBP",
    "¥": "CNY",
    "R$": "BRL",
    "A$": "AUD",
    "C$": "CAD",
}


PRODUCT_ID_PATTERNS = [
    re.compile(r"/item/(\d+)\.html"),
    re.compile(r"[?&]productId=(\d+)"),
    re.compile(r"/i/(\d+)"),
]


@dataclass
class ScrapeResult:
    product_id: str
    url: str
    title: Optional[str]
    price: float
    currency: Optional[str]
    raw_price_text: Optional[str] = None


class ScrapeError(Exception):
    """Raised when scraping fails or a price cannot be located."""


def extract_product_id(url: str) -> Optional[str]:
    """Try to extract the numeric AliExpress product id from a URL."""
    for pat in PRODUCT_ID_PATTERNS:
        m = pat.search(url)
        if m:
            return m.group(1)
    return None


def _normalize_price(text: str) -> Optional[tuple[float, Optional[str]]]:
    """Parse a price string like ``"US $12.34"`` into ``(12.34, 'USD')``."""
    if not text:
        return None
    text = text.strip()
    currency: Optional[str] = None
    for symbol, code in CURRENCY_SYMBOLS.items():
        if symbol in text:
            currency = code
            break
    # Strip currency symbols/letters, leaving digits, dot, comma.
    cleaned = re.sub(r"[^0-9.,]", "", text)
    if not cleaned:
        return None
    # Handle "1.234,56" (EU) vs "1,234.56" (US).
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        # If a single comma with 1-2 trailing digits, treat as decimal.
        if re.match(r"^\d+,\d{1,2}$", cleaned):
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    try:
        return float(cleaned), currency
    except ValueError:
        return None


def fetch_html(
    url: str,
    *,
    session: Optional[requests.Session] = None,
    timeout: float = 20.0,
    retries: int = 2,
    backoff: float = 2.0,
) -> tuple[str, str]:
    """Fetch a product page. Returns ``(final_url, html)``."""
    sess = session or requests.Session()
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
    }
    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            resp = sess.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            if resp.status_code >= 400:
                raise ScrapeError(
                    f"HTTP {resp.status_code} fetching {url}"
                )
            return resp.url, resp.text
        except (requests.RequestException, ScrapeError) as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(backoff * (attempt + 1))
    raise ScrapeError(f"Failed to fetch {url}: {last_exc}")


def _find_run_params(html: str) -> Optional[dict]:
    """Locate and parse the ``window.runParams`` JSON blob from the HTML."""
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        if "runParams" not in text:
            continue
        m = re.search(r"data\s*:\s*(\{.*?\})\s*,\s*csrfToken", text, re.DOTALL)
        if not m:
            m = re.search(r"window\.runParams\s*=\s*(\{.*?\});\s*</script>", text, re.DOTALL)
        if not m:
            m = re.search(r"runParams\s*=\s*(\{.*\})", text, re.DOTALL)
        if not m:
            continue
        raw = m.group(1)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            try:
                return json.loads(raw.rstrip(";"))
            except json.JSONDecodeError:
                continue
    return None


def _price_from_run_params(data: dict) -> Optional[tuple[float, Optional[str], Optional[str], Optional[str]]]:
    """Return (price, currency, title, raw_text) from a runParams dict."""
    root = data.get("data") if isinstance(data.get("data"), dict) else data

    title: Optional[str] = None
    title_module = root.get("titleModule") if isinstance(root, dict) else None
    if isinstance(title_module, dict):
        title = title_module.get("subject") or title_module.get("title")

    price_module = root.get("priceModule") if isinstance(root, dict) else None
    if not isinstance(price_module, dict):
        return None

    raw_candidates = [
        price_module.get("formatedActivityPrice"),
        price_module.get("formatedPrice"),
    ]
    for raw in raw_candidates:
        if isinstance(raw, str) and raw.strip():
            norm = _normalize_price(raw)
            if norm:
                price, currency = norm
                return price, currency, title, raw

    for key in ("minActivityAmount", "minAmount", "maxActivityAmount", "maxAmount"):
        amt = price_module.get(key)
        if isinstance(amt, dict):
            value = amt.get("value")
            currency = amt.get("currency")
            if value is not None:
                try:
                    return float(value), currency, title, str(value)
                except (TypeError, ValueError):
                    continue
    return None


def _price_from_jsonld(html: str) -> Optional[tuple[float, Optional[str], Optional[str], Optional[str]]]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("script", type="application/ld+json"):
        text = tag.string or tag.get_text() or ""
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        candidates = data if isinstance(data, list) else [data]
        for entry in candidates:
            if not isinstance(entry, dict):
                continue
            offers = entry.get("offers")
            title = entry.get("name")
            if isinstance(offers, dict):
                price = offers.get("price") or offers.get("lowPrice")
                currency = offers.get("priceCurrency")
                if price is not None:
                    try:
                        return float(price), currency, title, str(price)
                    except (TypeError, ValueError):
                        continue
    return None


def _price_from_meta(html: str) -> Optional[tuple[float, Optional[str], Optional[str], Optional[str]]]:
    soup = BeautifulSoup(html, "html.parser")
    title = None
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()
    elif soup.title and soup.title.string:
        title = soup.title.string.strip()

    price_meta = soup.find("meta", attrs={"property": "product:price:amount"}) or \
        soup.find("meta", attrs={"property": "og:price:amount"})
    currency_meta = soup.find("meta", attrs={"property": "product:price:currency"}) or \
        soup.find("meta", attrs={"property": "og:price:currency"})
    if price_meta and price_meta.get("content"):
        try:
            price = float(price_meta["content"])
        except ValueError:
            price = None
        if price is not None:
            currency = currency_meta["content"] if currency_meta and currency_meta.get("content") else None
            return price, currency, title, price_meta["content"]
    return None


def scrape(url: str, *, session: Optional[requests.Session] = None) -> ScrapeResult:
    """Scrape a single AliExpress product URL and return a :class:`ScrapeResult`."""
    parsed = urlparse(url)
    if "aliexpress" not in parsed.netloc.lower():
        raise ScrapeError(f"Not an AliExpress URL: {url}")

    final_url, html = fetch_html(url, session=session)

    product_id = extract_product_id(final_url) or extract_product_id(url)
    if not product_id:
        raise ScrapeError(f"Could not determine product id from URL: {final_url}")

    extractors = (
        lambda: _price_from_run_params(_find_run_params(html) or {}),
        lambda: _price_from_jsonld(html),
        lambda: _price_from_meta(html),
    )
    last_title: Optional[str] = None
    for extractor in extractors:
        result = extractor()
        if not result:
            continue
        price, currency, title, raw = result
        if title:
            last_title = title
        if price is not None:
            return ScrapeResult(
                product_id=product_id,
                url=final_url,
                title=title or last_title,
                price=float(price),
                currency=currency,
                raw_price_text=raw,
            )

    raise ScrapeError(
        f"Could not extract a price from {final_url}. "
        "AliExpress may have changed its markup or the page may require "
        "JavaScript rendering. Open the URL in a browser to confirm."
    )
