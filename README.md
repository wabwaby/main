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

The **same 403 applies to the card art**, so this backend also downloads
the image bytes with the browser headers and re-hosts them in a public
Supabase Storage bucket. The `image_url` we save in the `cards` table
points at the Supabase CDN, not Bandai — so `<img src={card.image_url}>` on
the frontend just works.

## Project layout

```
.
├── src/
│   ├── server.js      # Express app + /api/fetch-and-store-card
│   ├── bandai.js      # fetch + parse card page (axios + cheerio)
│   ├── images.js      # download card art + upload to Supabase Storage
│   └── supabase.js    # service-role client
├── supabase/
│   └── schema.sql     # cards table + indexes + RLS
├── .env.example
├── package.json
└── README.md
```

## 1. Create the Supabase table + storage bucket

Open the Supabase dashboard → **SQL Editor** → paste `supabase/schema.sql`
and run it. It creates:

- `public.cards` with the columns from the spec plus `created_at` /
  `updated_at`, a trigram index on `card_name`, and read-only RLS (writes
  go through the service role from this backend).
- A **public** storage bucket named `card-images` for re-hosted card art.

The bucket has to exist before the first scrape, otherwise the image
rehost step will fail (the card row still gets saved; `image_url` just
stays `null` until you re-run the scrape).

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
    "text_data": {
      "raw": { "...": "..." },
      "source_image_url": "https://www.gundam-gcg.com/.../ST01-001.png"
    },
    "image_url": "https://<project>.supabase.co/storage/v1/object/public/card-images/cards/ST01-001.png",
    "raw_bandai_url": "https://www.gundam-gcg.com/en/cards/index.php?...",
    "created_at": "...",
    "updated_at": "..."
  },
  "imageWarning": null
}
```

Notice that `image_url` points at **Supabase Storage**, not Bandai — so the
browser can render it without hitting 403/CORS. The original Bandai URL is
preserved in `text_data.source_image_url` for provenance.

If the image download or upload fails (bucket missing, timeout, etc.) the
card row is still saved with `image_url: null` and the reason is returned
in `imageWarning`. Re-POST the same `cardId` once you've fixed the cause
and the row is updated in place.

Calling it again for the same `cardId` is an upsert — rows are keyed on the
card's serial number, so re-scrapes refresh the record (and overwrite the
stored image) in place.

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
