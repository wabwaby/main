# aliprice — a local AliExpress price tracker

A small Python CLI that watches the AliExpress products you care about and tells
you when there's a significant price drop. Everything runs locally; price
history lives in a SQLite database in your home directory.

You can use it from the terminal or open the generated HTML dashboard in your
browser.

> ⚠️ AliExpress doesn't offer a free, official price-history API. This tool
> scrapes the public product page (the same JSON blob the site itself uses).
> The site occasionally changes its markup and has anti-bot measures, so
> expect to tweak the scraper now and then. Use this for personal tracking,
> respect AliExpress's terms of service, and don't hammer their servers.

## Install

Requires Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Optional: add an alias so you can run it from anywhere:

```bash
alias aliprice="python -m aliprice"
```

The examples below use `python -m aliprice`.

## Quick start

```bash
# 1) Start tracking some items (copy the product URL from your browser).
python -m aliprice add "https://www.aliexpress.com/item/1005006123456789.html" --nickname headphones
python -m aliprice add "https://www.aliexpress.com/item/1005005987654321.html"

# 2) Refresh current prices for everything you track.
python -m aliprice check

# 3) See what's on sale right now.
python -m aliprice deals

# 4) Or open a local dashboard in your browser.
python -m aliprice report --open
```

## Commands

| Command | What it does |
| --- | --- |
| `add <url> [--nickname NAME]` | Start tracking a product. Fetches the first price immediately (use `--no-fetch` to skip). |
| `remove <id-or-alias>` | Stop tracking a product. |
| `list` | Show all tracked products with their latest and lowest prices. |
| `check [id-or-alias]` | Re-fetch prices. With no argument, refreshes everything. |
| `deals [--all]` | Show items whose current price is a meaningful drop vs. their history. |
| `history <id-or-alias>` | Print the full price history for one product. |
| `report [-o out.html] [--open]` | Render a self-contained HTML dashboard you can open locally. |

By default the SQLite DB lives at `~/.aliprice/aliprice.sqlite3`. Override with
the `--db PATH` flag or the `ALIPRICE_DB` environment variable.

## What counts as a "deal"

`aliprice deals` surfaces any product where at least one of the following
holds (after at least two data points):

- **All-time low** and the current price is ≥ 5% below the long-term average.
- Current price is ≥ 10% below the long-term average.
- Current price is ≥ 8% below the previously recorded price.

These thresholds live in `aliprice/deals.py` (`DealSignal.is_deal`) if you
want to tune them to your taste.

## Automating it

If you want the tracker to run on its own and show you deals whenever you
open it:

- **macOS / Linux (cron):**
  ```cron
  # refresh every 6 hours
  0 */6 * * * cd /path/to/repo && /path/to/.venv/bin/python -m aliprice check >/dev/null
  ```
- **Windows (Task Scheduler):** create a basic task that runs
  `python -m aliprice check` on a schedule.

Then make a one-line launcher that refreshes + opens the dashboard:

```bash
python -m aliprice check && python -m aliprice report --open
```

## How the scraper works

`aliprice/scraper.py` does the heavy lifting:

1. Fetches the product page with a realistic browser User-Agent.
2. Locates the `window.runParams` JSON blob (the same data AliExpress's own
   React app reads). Pulls `priceModule.formatedActivityPrice` /
   `formatedPrice` and the title.
3. Falls back to JSON-LD blocks (`application/ld+json`) and finally to
   OpenGraph / `<meta>` tags if the primary blob isn't there.

If AliExpress changes their markup and a fetch starts failing, the error
message will tell you which URL broke; open it in a browser, look at the
page source, and adjust the patterns in `scraper.py`.

## Project layout

```
aliprice/
  __init__.py
  __main__.py     # so `python -m aliprice ...` works
  cli.py          # argparse CLI + rich output
  storage.py      # SQLite layer (products + price_history)
  scraper.py      # AliExpress HTML/JSON parsing
  deals.py        # Price-drop heuristics
  report.py       # Local HTML dashboard
requirements.txt
README.md
```
