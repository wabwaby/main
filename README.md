# gundam-card-proxy

A tiny Node.js/Express backend that fetches Gundam Card Game card data from
Bandai's site server-side (bypassing browser CORS/403), parses it, and
upserts it into a Supabase `cards` table.

## Why

The browser can't talk to `gundam-gcg.com` directly — Bandai's CDN rejects
cross-origin requests (CORS) and blocks obvious non-browser user-agents with
`403 Forbidden`. This proxy runs server-side, sends a realistic browser
`User-Agent`, and writes the normalized result straight into Supabase so the
frontend only ever reads from your own DB.

## Project layout

```
.
├── src/
│   ├── server.js      # Express app + /api/fetch-and-store-card
│   ├── bandai.js      # fetch + parse (axios + cheerio)
│   └── supabase.js    # service-role client
├── supabase/
│   └── schema.sql     # cards table + indexes + RLS
├── .env.example
├── package.json
└── README.md
```

## 1. Create the Supabase table

Open the Supabase dashboard → **SQL Editor** → paste `supabase/schema.sql`
and run it. It creates `public.cards` with the columns from the spec plus
`created_at` / `updated_at`, a trigram index on `card_name`, and read-only
RLS (writes go through the service role from this backend).

## 2. Configure environment

```bash
cp .env.example .env
```

Fill in:

- `SUPABASE_URL` — your project URL
- `SUPABASE_SERVICE_ROLE_KEY` — **server-side only**, never ship to the browser
- `ALLOWED_ORIGINS` — comma-separated list of frontends allowed to call this proxy
- `PORT` — defaults to `3001`

## 3. Install and run

```bash
npm install
npm run dev       # auto-reload (node --watch)
# or
npm start
```

You should see:

```
gundam-card-proxy listening on http://localhost:3001
```

Health check:

```bash
curl http://localhost:3001/healthz
```

## 4. Fetch and store a card

By card number:

```bash
curl -X POST http://localhost:3001/api/fetch-and-store-card \
  -H 'content-type: application/json' \
  -d '{"cardId":"ST01-001"}'
```

By direct Bandai URL:

```bash
curl -X POST http://localhost:3001/api/fetch-and-store-card \
  -H 'content-type: application/json' \
  -d '{"url":"https://www.gundam-gcg.com/en/cards/index.php?search=true&keyword_type%5B%5D=no&keyword=ST01-001"}'
```

Response (200):

```json
{
  "card": {
    "id": "ST01-001",
    "card_name": "Gundam",
    "card_number": "ST01-001",
    "type": "Unit",
    "color": "Blue",
    "text_data": { "raw": { "...": "..." } },
    "image_url": "https://www.gundam-gcg.com/.../images/cards/card/ST01-001.png",
    "raw_bandai_url": "https://www.gundam-gcg.com/en/cards/index.php?...",
    "created_at": "...",
    "updated_at": "..."
  }
}
```

Calling it again for the same `cardId` is an upsert — rows are keyed on the
card's serial number, so re-scrapes refresh the record in place.

## Security notes

- The **service role key** has god-mode over your Supabase project. Keep it
  in `.env` on the server; never expose it to the browser, never commit it,
  and rotate it immediately if it leaks.
- `ALLOWED_ORIGINS` gates browser callers. Server-to-server callers (no
  `Origin` header) are allowed through — put this proxy behind your own auth
  (API key, Supabase JWT, etc.) before opening it to the public internet.
- The scraper sends one request per call and respects a 15s timeout. If you
  batch-import a full set, add your own rate limiting and be a good citizen.

## Adapting the parser

`src/bandai.js` tries several common markup patterns (`<dl>` pairs,
`.dataTxt`-style rows, OG meta tags) and stores everything it couldn't
classify in `text_data.raw` so nothing is lost. When Bandai tweaks their
markup, update `parseHtml()` — the rest of the pipeline doesn't need to
change.
