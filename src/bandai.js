const axios = require('axios');
const cheerio = require('cheerio');

// The card *list* page is a filter UI; the actual card data lives on the
// detail page. We always resolve a bare card id to the detail URL.
const DEFAULT_DETAIL_URL =
    process.env.BANDAI_CARD_DETAIL_URL || 'https://www.gundam-gcg.com/en/cards/detail.php';

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
        const u = new URL(DEFAULT_DETAIL_URL);
        u.searchParams.set('detailSearch', cardId.trim());
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
 * Extract card data from a gundam-gcg.com detail page.
 *
 * Observed structure (ST01-001):
 *   .cardNo       → "ST01-001"
 *   .cardName     → "Gundam"
 *   .cardImage img[src] → "../images/cards/card/ST01-001.webp?261016"
 *   .dataBox > .dataTit + .dataTxt   → labeled rows (Lv., COST, COLOR, TYPE,
 *                                       Zone, Trait, Link, AP, HP,
 *                                       Source Title, Where to get it)
 *   .cardDataRow > .dataTxt.isRegular (no dataTit) → the card's rules /
 *                                                     effect text block
 *
 * We normalize the common fields and keep everything in `raw` so any extra
 * labels Bandai introduces are still captured.
 */
function parseHtml(html, sourceUrl) {
    const $ = cheerio.load(html);

    const raw = {};

    // Labeled .dataBox pairs.
    $('.dataBox').each((_, el) => {
        const $el = $(el);
        const label = $el.find('.dataTit').first().text().replace(/\s+/g, ' ').trim();
        const value = $el.find('.dataTxt').first().text().replace(/\s+/g, ' ').trim();
        if (label && value) raw[label.toLowerCase()] = value;
    });

    // Rules / effect text: .dataTxt that isn't paired with a .dataTit.
    // Preserve line breaks (Bandai separates effects with <br>).
    const effectParts = [];
    $('.cardDataRow > .dataTxt, .cardDataRow .dataTxt.isRegular').each((_, el) => {
        const $el = $(el);
        // Replace <br> with newlines so effects stay readable.
        $el.find('br').replaceWith('\n');
        const text = $el.text().replace(/[ \t]+/g, ' ').replace(/\n[ \t]+/g, '\n').trim();
        if (text) effectParts.push(text);
    });
    const effectText = effectParts.join('\n\n');
    if (effectText) raw['effect'] = effectText;

    // Direct selectors for the structured fields.
    const cardNumber =
        $('.cardNo').first().text().trim() || null;
    const cardName =
        $('.cardName').first().text().trim() || null;

    // Image lives in .cardImage; fall back to og:image only if nothing better.
    const rawImg =
        $('.cardImage img').first().attr('src') ||
        $('.cardImage img').first().attr('data-src') ||
        $('meta[property="og:image"]').attr('content');
    const sourceImageUrl = rawImg ? new URL(rawImg, sourceUrl).toString() : null;

    const fields = {
        card_number: cardNumber,
        card_name: cardName,
        type: raw['type'] || null,       // "UNIT", "COMMAND", "PILOT", "BASE", "RESOURCE"
        color: raw['color'] || null,     // "Blue", "Green", "Red", "White", "Purple"
        source_image_url: sourceImageUrl,
    };

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
