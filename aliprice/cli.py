"""Command-line interface for the AliExpress local price tracker."""

from __future__ import annotations

import argparse
import sys
import time
import webbrowser
from typing import Iterable, Optional

import requests
from rich.console import Console
from rich.table import Table

from . import __version__
from .deals import DealSignal, evaluate
from .report import build as build_report
from .scraper import ScrapeError, ScrapeResult, extract_product_id, scrape
from .storage import Product, Storage

console = Console()


def _format_price(price: Optional[float], currency: Optional[str]) -> str:
    if price is None:
        return "—"
    cur = (currency + " ") if currency else ""
    return f"{cur}{price:.2f}"


def _check_one(
    storage: Storage,
    product: Product,
    *,
    session: requests.Session,
    verbose: bool = False,
) -> Optional[ScrapeResult]:
    try:
        result = scrape(product.url, session=session)
    except ScrapeError as exc:
        console.print(f"[red]error[/] {product.product_id}: {exc}")
        return None
    storage.record_price(
        result.product_id, result.price, result.currency
    )
    storage.update_metadata(
        result.product_id,
        title=result.title,
        currency=result.currency,
    )
    history = storage.history(result.product_id)
    refreshed = storage.get_product(result.product_id) or product
    signal = evaluate(refreshed, history)
    label = result.title or product.nickname or result.product_id
    label = label[:70] + ("…" if len(label) > 70 else "")
    price_str = _format_price(result.price, result.currency)
    extra = ""
    if signal:
        if signal.is_deal:
            extra = f"  [bold green]✓ {signal.headline}[/]"
        elif signal.samples >= 2:
            extra = f"  [dim]({signal.headline})[/]"
    console.print(f"[cyan]{result.product_id}[/] {price_str}  {label}{extra}")
    if verbose:
        console.print(
            f"    avg={_format_price(signal.average_price if signal else None, result.currency)} "
            f"low={_format_price(signal.lowest_price if signal else None, result.currency)} "
            f"samples={signal.samples if signal else 0}"
        )
    return result


def cmd_add(args: argparse.Namespace) -> int:
    storage = Storage(args.db) if args.db else Storage()
    pid = extract_product_id(args.url)
    if not pid:
        console.print(f"[red]Could not parse product id from URL:[/] {args.url}")
        return 2

    storage.add_product(
        product_id=pid,
        url=args.url,
        nickname=args.nickname,
    )
    console.print(f"[green]added[/] {pid}  {args.url}")
    if not args.no_fetch:
        session = requests.Session()
        product = storage.get_product(pid)
        if product:
            _check_one(storage, product, session=session)
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    storage = Storage(args.db) if args.db else Storage()
    product = storage.find_product(args.product)
    if not product:
        console.print(f"[red]not found:[/] {args.product}")
        return 1
    storage.remove_product(product.product_id)
    console.print(f"[yellow]removed[/] {product.product_id}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    storage = Storage(args.db) if args.db else Storage()
    products = storage.list_products()
    if not products:
        console.print("[dim]no products tracked. add one with: aliprice add <url>[/]")
        return 0
    table = Table(show_header=True, header_style="bold")
    table.add_column("ID")
    table.add_column("Alias")
    table.add_column("Title", max_width=50)
    table.add_column("Current", justify="right")
    table.add_column("Lowest", justify="right")
    table.add_column("Samples", justify="right")
    table.add_column("Last checked")
    for p in products:
        latest = storage.latest_price(p.product_id)
        history = storage.history(p.product_id)
        signal = evaluate(p, history)
        current = _format_price(latest.price if latest else None, latest.currency if latest else p.currency)
        lowest = _format_price(signal.lowest_price if signal else None, p.currency)
        samples = str(signal.samples) if signal else "0"
        table.add_row(
            p.product_id,
            p.nickname or "",
            p.title or "",
            current,
            lowest,
            samples,
            p.last_checked or "—",
        )
    console.print(table)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    storage = Storage(args.db) if args.db else Storage()
    if args.product:
        product = storage.find_product(args.product)
        if not product:
            console.print(f"[red]not found:[/] {args.product}")
            return 1
        targets = [product]
    else:
        targets = storage.list_products()
    if not targets:
        console.print("[dim]nothing to check[/]")
        return 0

    session = requests.Session()
    for i, product in enumerate(targets):
        _check_one(storage, product, session=session, verbose=args.verbose)
        if i < len(targets) - 1 and args.delay > 0:
            time.sleep(args.delay)
    return 0


def cmd_deals(args: argparse.Namespace) -> int:
    storage = Storage(args.db) if args.db else Storage()
    products = storage.list_products()
    signals: list[DealSignal] = []
    for p in products:
        sig = evaluate(p, storage.history(p.product_id))
        if sig and (args.all or sig.is_deal):
            signals.append(sig)
    if not signals:
        console.print("[dim]no deals right now. run `aliprice check` to refresh.[/]")
        return 0
    signals.sort(key=lambda s: s.drop_vs_average_pct, reverse=True)
    table = Table(show_header=True, header_style="bold green", title="Deals")
    table.add_column("ID")
    table.add_column("Title", max_width=48)
    table.add_column("Price", justify="right")
    table.add_column("vs avg", justify="right")
    table.add_column("vs low", justify="right")
    table.add_column("Note")
    for s in signals:
        table.add_row(
            s.product.product_id,
            s.product.title or s.product.nickname or "",
            _format_price(s.current_price, s.currency),
            f"{s.drop_vs_average_pct:+.1f}%",
            f"{s.drop_vs_lowest_pct:+.1f}%",
            s.headline,
        )
    console.print(table)
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    storage = Storage(args.db) if args.db else Storage()
    product = storage.find_product(args.product)
    if not product:
        console.print(f"[red]not found:[/] {args.product}")
        return 1
    history = storage.history(product.product_id)
    if not history:
        console.print("[dim]no price points recorded yet[/]")
        return 0
    table = Table(show_header=True, header_style="bold")
    table.add_column("Captured at")
    table.add_column("Price", justify="right")
    for p in history:
        table.add_row(p.captured_at, _format_price(p.price, p.currency))
    console.print(table)
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    storage = Storage(args.db) if args.db else Storage()
    out = build_report(storage, args.output)
    console.print(f"[green]report written:[/] {out}")
    if args.open:
        webbrowser.open(f"file://{out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aliprice",
        description="Local AliExpress price tracker — watch deals on items you care about.",
    )
    parser.add_argument(
        "--db",
        help="Path to the SQLite database (default: ~/.aliprice/aliprice.sqlite3 "
        "or $ALIPRICE_DB).",
    )
    parser.add_argument("--version", action="version", version=f"aliprice {__version__}")

    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="Start tracking a product URL.")
    p_add.add_argument("url", help="AliExpress product URL.")
    p_add.add_argument("--nickname", help="Short alias for this product.")
    p_add.add_argument(
        "--no-fetch",
        action="store_true",
        help="Don't fetch the current price immediately.",
    )
    p_add.set_defaults(func=cmd_add)

    p_rm = sub.add_parser("remove", help="Stop tracking a product (by id or alias).")
    p_rm.add_argument("product")
    p_rm.set_defaults(func=cmd_remove)

    p_ls = sub.add_parser("list", help="List all tracked products.")
    p_ls.set_defaults(func=cmd_list)

    p_check = sub.add_parser(
        "check", help="Fetch latest prices (all tracked, or one by id/alias)."
    )
    p_check.add_argument("product", nargs="?", help="Specific product id or alias.")
    p_check.add_argument(
        "--delay", type=float, default=2.0, help="Seconds between requests (default 2)."
    )
    p_check.add_argument("-v", "--verbose", action="store_true")
    p_check.set_defaults(func=cmd_check)

    p_deals = sub.add_parser("deals", help="Show items with significant price drops.")
    p_deals.add_argument("--all", action="store_true", help="Show all products, not just deals.")
    p_deals.set_defaults(func=cmd_deals)

    p_hist = sub.add_parser("history", help="Show price history for a product.")
    p_hist.add_argument("product")
    p_hist.set_defaults(func=cmd_history)

    p_report = sub.add_parser("report", help="Generate a local HTML dashboard.")
    p_report.add_argument(
        "-o", "--output", default="aliprice-report.html", help="Output HTML path."
    )
    p_report.add_argument("--open", action="store_true", help="Open the report in your browser.")
    p_report.set_defaults(func=cmd_report)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        console.print("\n[dim]interrupted[/]")
        return 130


if __name__ == "__main__":
    sys.exit(main())
