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

## "But I don't know which URLs to track"

That's fine — AliExpress already keeps lists of items you care about, and
the tool can read them as you:

- Your **wishlist** (the heart icon) — the strongest "watch this" signal.
- Your **cart** — items you considered buying.
- Any **listing page** you can see in a browser (category, search results,
  a shared list).

To unlock that, you log in once via your browser's cookies. AliExpress's
recommendation algorithm itself isn't exposed by any public API, but these
are the realistic equivalents of "stuff I normally see in the app".

### One-time login

1. Open `aliexpress.com` in your browser while logged in.
2. Open DevTools → Network tab → click any request to the site.
3. In the request headers, copy the entire **`Cookie:`** value.
4. Paste it into the tool:

   ```bash
   python -m aliprice login --cookie "ali_apache_id=...; aep_usuc_f=...; xman_t=...; ..."
   ```

   Alternatively, export a Netscape-format `cookies.txt` using a browser
   extension like *"Get cookies.txt LOCALLY"* and point the tool at it:

   ```bash
   python -m aliprice login --cookies-file ~/Downloads/aliexpress-cookies.txt
   ```

Credentials are stored at `~/.aliprice/config.json` (chmod 600). Run
`aliprice login --clear` to forget them. AliExpress invalidates sessions
periodically; if `discover` stops finding things, refresh the cookie.

### Auto-discover what to track

```bash
# Preview what's in your wishlist (and cart, if you add --cart):
python -m aliprice discover --cart

# Like what you see? Add all of them to the tracker in one go:
python -m aliprice discover --cart --auto-add

# Or scan any listing-style page — works without logging in:
python -m aliprice discover --url "https://www.aliexpress.com/category/200000532/cellphones.html"
```

`discover` extracts every product reference (`/item/<id>.html`) from the
page, deduplicates, and either prints them or registers them with `--auto-add`.
After auto-adding it also fetches the current price for each new product so
you start with a baseline data point.

### Bulk import from a list of URLs

If you already have a chunk of URLs lying around (browser history, a Notes
file, etc.), skip the cookie dance entirely:

```bash
# Three ways to feed it URLs:
python -m aliprice import https://.../item/100.html https://.../item/200.html
python -m aliprice import --file my-urls.txt
pbpaste | python -m aliprice import          # macOS clipboard, one URL per line
```

## Commands

| Command | What it does |
| --- | --- |
| `add <url> [--nickname NAME]` | Start tracking a single product. Fetches the first price immediately. |
| `remove <id-or-alias>` | Stop tracking a product. |
| `list` | Show all tracked products with their latest and lowest prices. |
| `check [id-or-alias]` | Re-fetch prices. With no argument, refreshes everything. |
| `deals [--all]` | Show items whose current price is a meaningful drop vs. their history. |
| `history <id-or-alias>` | Print the full price history for one product. |
| `login [--cookie ...] [--cookies-file ...] [--clear]` | Save/clear AliExpress session credentials. |
| `discover [--wishlist] [--cart] [--url URL] [--auto-add]` | Find products from your wishlist, cart, or any listing page. |
| `import [urls...] [--file PATH]` | Bulk-add a list of URLs (args, file, or stdin). |
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

## Honest limitations

- **There is no public AliExpress price-history API.** This tool builds the
  history itself by recording prices over time. The longer you let it run,
  the better its sense of "normal" gets — which makes the deal heuristic
  more useful.
- **AliExpress's actual recommendation algorithm is private.** No third-party
  tool can tap it. The closest proxies — wishlist, cart, recently viewed,
  and pages you choose to browse — are what `discover` works with.
- **JS-heavy pages** sometimes hold off rendering data until after page
  load. The single-product scraper handles this fine (the product page
  embeds prices in `window.runParams`), but a few listing pages defer their
  product cards to XHR calls; if `discover` returns 0 items on a page that
  clearly has products, you'd need a real-browser tool like Playwright in
  the loop. The natural extension point is
  [`aliprice/scraper.py::fetch_html`](aliprice/scraper.py).

## Project layout

```
aliprice/
  __init__.py
  __main__.py     # so `python -m aliprice ...` works
  cli.py          # argparse CLI + rich output
  storage.py      # SQLite layer (products + price_history)
  scraper.py      # AliExpress HTML/JSON parsing + link extraction
  session.py      # Cookie / config management
  deals.py        # Price-drop heuristics
  report.py       # Local HTML dashboard
requirements.txt
scripts/smoke_test.py   # Offline checks for every module
README.md
```
