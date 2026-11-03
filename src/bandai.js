const axios = require('axios');
const cheerio = require('cheerio');

const DEFAULT_BASE_URL =
    process.env.BANDAI_CARD_BASE_URL || 'https://www.gundam-gcg.com/en/cards/index.php';

// A realistic desktop Chrome UA — Bandai's CDN returns 403 for obvious
// scraper user-agents (curl/axios/python-requests/etc.).
const BROWSER_HEADERS = {
    'User-Agent':
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
        '(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
    Accept:
        'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,' +
        'image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Cache-Control': 'no-cache',
    Pragma: 'no-cache',
    Referer: 'https://www.gundam-gcg.com/en/cards/',
};

/**
 * Resolve the source URL to scrape. Accepts either a full Bandai URL or a
 * bare card number like "ST01-001".
 */
function resolveSourceUrl({ url, cardId }) {
    if (url) {
        const parsed = new URL(url); // throws TypeError on garbage input
        return parsed.toString();
    }
    if (cardId) {
        const u = new URL(DEFAULT_BASE_URL);
        u.searchParams.set('search', 'true');
        u.searchParams.set('keyword_type[]', 'no');
        u.searchParams.set('keyword', cardId);
        return u.toString();
    }
    throw new Error('Provide either `url` or `cardId`.');
}

async function fetchSource(sourceUrl) {
    const res = await axios.get(sourceUrl, {
        headers: BROWSER_HEADERS,
        timeout: 15_000,
        // Follow redirects (Bandai sometimes 302s through a locale picker).
        maxRedirects: 5,
        // Treat 4xx as errors but surface the status in the thrown error.
        validateStatus: (s) => s >= 200 && s < 400,
        responseType: 'text',
        transformResponse: [(data) => data],
    });
    return { contentType: res.headers['content-type'] || '', body: res.data };
}

/**
 * Best-effort extractor for Bandai card detail pages. Bandai's markup changes
 * occasionally, so we try several common patterns (dt/dd pairs, labeled rows,
 * then fall back to meta tags) and keep anything we couldn't classify in
 * `text_data.raw` for the frontend to display verbatim.
 */
function parseHtml(html, sourceUrl) {
    const $ = cheerio.load(html);

    const fields = {};
    const raw = {};

    // Pattern 1: <dl><dt>Label</dt><dd>Value</dd>…</dl>
    $('dl').each((_, dl) => {
        const $dl = $(dl);
        const dts = $dl.find('dt');
        const dds = $dl.find('dd');
        dts.each((i, dt) => {
            const label = $(dt).text().trim().toLowerCase();
            const value = $(dds[i]).text().trim();
            if (label && value) raw[label] = value;
        });
    });

    // Pattern 2: rows like <div class="dataTxt"><span class="label">…</span>Value</div>
    $('[class*="dataBox"], [class*="dataTxt"], [class*="data_txt"]').each((_, el) => {
        const $el = $(el);
        const label = $el.find('.label, .dataTtl, .data_ttl, h4, h5').first().text().trim().toLowerCase();
        const valueEl = $el.clone();
        valueEl.find('.label, .dataTtl, .data_ttl, h4, h5').remove();
        const value = valueEl.text().replace(/\s+/g, ' ').trim();
        if (label && value) raw[label] = value;
    });

    const pick = (...keys) => {
        for (const k of keys) {
            const hit = Object.keys(raw).find((rk) => rk.includes(k));
            if (hit) return raw[hit];
        }
        return undefined;
    };

    fields.card_number = pick('card no', 'card number', 'number', 'no.') ||
        $('meta[name="card_no"]').attr('content');

    fields.card_name = pick('card name', 'name') ||
        $('h1, .cardName, .card_name').first().text().trim() ||
        $('meta[property="og:title"]').attr('content');

    fields.type  = pick('card type', 'type');
    fields.color = pick('color', 'colour');

    // Grab the main card image if we can find one. We keep this as the
    // SOURCE url (Bandai CDN). The server will download the bytes and
    // re-host them on Supabase Storage before writing `image_url`.
    const img =
        $('.cardImg img, .card_img img, .cardImage img').first().attr('src') ||
        $('meta[property="og:image"]').attr('content');
    if (img) {
        fields.source_image_url = new URL(img, sourceUrl).toString();
    }

    return { fields, raw };
}

function parseJson(body) {
    const data = JSON.parse(body);
    // Bandai doesn't currently expose a public JSON API, but if a user points
    // this at an internal endpoint we at least do something sensible.
    const node = Array.isArray(data) ? data[0] : data.card || data.data || data;
    return {
        fields: {
            card_number: node?.card_no || node?.cardNumber || node?.number,
            card_name: node?.card_name || node?.name,
            type: node?.card_type || node?.type,
            color: node?.color,
            source_image_url: node?.image_url || node?.img,
        },
        raw: node || {},
    };
}

/**
 * Fetch and normalize a single card. Returns a row ready for upsert into
 * the `cards` table (keys match the schema).
 */
async function fetchCard({ url, cardId }) {
    const sourceUrl = resolveSourceUrl({ url, cardId });
    const { contentType, body } = await fetchSource(sourceUrl);

    const parsed = contentType.includes('application/json')
        ? parseJson(body)
        : parseHtml(body, sourceUrl);

    const { fields, raw } = parsed;

    const cardNumber = (fields.card_number || cardId || '').trim();
    if (!cardNumber) {
        const err = new Error(
            'Could not determine card_number from the Bandai response. ' +
                'Pass `cardId` explicitly or check that the URL points at a card detail page.',
        );
        err.status = 422;
        throw err;
    }

    return {
        // Row to upsert (minus image_url, which the server fills in after
        // re-hosting the image to Supabase Storage).
        row: {
            id: cardNumber,
            card_name: (fields.card_name || '').trim() || cardNumber,
            card_number: cardNumber,
            type: fields.type?.trim() || null,
            color: fields.color?.trim() || null,
            text_data: {
                raw,
                // Keep the original Bandai image URL for provenance /
                // re-scrape, even after we rehost the bytes.
                source_image_url: fields.source_image_url || null,
            },
            image_url: null,
            raw_bandai_url: sourceUrl,
        },
        sourceImageUrl: fields.source_image_url || null,
    };
}

module.exports = { fetchCard, resolveSourceUrl };
