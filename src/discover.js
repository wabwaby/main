const axios = require('axios');
const cheerio = require('cheerio');

const { BROWSER_HEADERS } = require('./http');

const INDEX_URL =
    process.env.BANDAI_CARD_INDEX_URL || 'https://www.gundam-gcg.com/en/cards/index.php';

async function fetchHtml(url, { method = 'GET', body } = {}) {
    const res = await axios({
        url,
        method,
        headers: {
            ...BROWSER_HEADERS,
            ...(method === 'POST' ? { 'Content-Type': 'application/x-www-form-urlencoded' } : {}),
        },
        data: body,
        timeout: 20_000,
        maxRedirects: 5,
        responseType: 'text',
        transformResponse: [(d) => d],
        validateStatus: (s) => s >= 200 && s < 400,
    });
    return res.data;
}

/**
 * Discover every product/set Bandai exposes in the card filter UI.
 *
 * The landing page contains a dropdown of `js-selectBtn-package` buttons;
 * each has `data-val="<6-digit-internal-id>"` and visible text like
 * "Heroic Beginnings [ST01]". We parse both so callers can target a set by
 * either the short code (`ST01`) or the internal id (`616001`).
 *
 * Future sets are picked up automatically — Bandai adds them to the same
 * dropdown.
 *
 * Returns: [{ internalId, code, displayName, rawLabel }]
 *   internalId: "616001"
 *   code:       "ST01"  (parsed from the bracketed suffix; may be null for
 *                        buckets like "Basic Cards" / "Promotion card")
 *   displayName:"Heroic Beginnings"
 *   rawLabel:   "Heroic Beginnings [ST01]"
 */
async function discoverSets() {
    const html = await fetchHtml(INDEX_URL);
    const $ = cheerio.load(html);
    const seen = new Set();
    const sets = [];

    $('.js-selectBtn-package').each((_, el) => {
        const $el = $(el);
        const internalId = ($el.attr('data-val') || '').trim();
        if (!internalId) return; // the "ALL" entry has an empty value
        if (seen.has(internalId)) return;
        seen.add(internalId);

        const rawLabel = $el.text().replace(/\s+/g, ' ').trim();
        const bracket = rawLabel.match(/\[([^\]]+)\]/);
        const code = bracket ? bracket[1] : null;
        const displayName = rawLabel.replace(/\s*\[[^\]]+\]\s*$/, '').trim();

        sets.push({ internalId, code, displayName, rawLabel });
    });

    return sets;
}

/**
 * Resolve a user-friendly set hint (short code like "ST01", internal id,
 * or display label) to a set descriptor. Case-insensitive on `code`.
 */
async function resolveSet(hint, cached) {
    const sets = cached || (await discoverSets());
    const h = String(hint).trim();
    const byInternal = sets.find((s) => s.internalId === h);
    if (byInternal) return byInternal;
    const byCode = sets.find((s) => s.code && s.code.toLowerCase() === h.toLowerCase());
    if (byCode) return byCode;
    const byLabel = sets.find(
        (s) => s.rawLabel.toLowerCase() === h.toLowerCase() ||
            s.displayName.toLowerCase() === h.toLowerCase(),
    );
    if (byLabel) return byLabel;
    throw new Error(`Unknown set: ${hint}`);
}

/**
 * List every card (grouped by base id, with every variant) in a set.
 *
 * Bandai returns the whole set in a single POST response — the client-side
 * pager is purely cosmetic — so this is one request per set. Each
 * `<li class="cardItem">` is one image variant; its parent anchor's
 * `data-src="detail.php?detailSearch=<cardId>"` carries the real id
 * (href is `javascript:void(0);`). Alt arts have ids like `GD01-001_p1`.
 *
 * We group variants under their base id (stripping `_pN`).
 *
 * Returns: [
 *   {
 *     baseId: "GD01-001",
 *     variants: [
 *       { code: "",   detailId: "GD01-001",    sourceImageUrl: "https://…/GD01-001.webp?…" },
 *       { code: "p1", detailId: "GD01-001_p1", sourceImageUrl: "https://…/GD01-001_p1.webp?…" },
 *       …
 *     ],
 *   },
 *   …
 * ]
 */
async function discoverSetCards(setInternalId) {
    const html = await fetchHtml(INDEX_URL, {
        method: 'POST',
        body: `package=${encodeURIComponent(setInternalId)}`,
    });

    const $ = cheerio.load(html);
    const byBase = new Map();

    $('.cardItem').each((_, el) => {
        const $el = $(el);
        const a = $el.find('a').first();
        const detailSrc = a.attr('data-src') || a.attr('href') || '';
        const idMatch = detailSrc.match(/detailSearch=([A-Z0-9_-]+)/i);
        if (!idMatch) return;
        const detailId = idMatch[1];

        const img = $el.find('img').first();
        const rawImg = img.attr('data-src') || img.attr('src') || '';
        if (!rawImg || rawImg.includes('/parts/')) return; // skip placeholder gif
        const sourceImageUrl = new URL(rawImg, INDEX_URL).toString();

        const varMatch = detailId.match(/^(.+?)_p(\d+)$/i);
        const baseId = varMatch ? varMatch[1] : detailId;
        const code = varMatch ? `p${varMatch[2]}` : '';

        if (!byBase.has(baseId)) byBase.set(baseId, []);
        byBase.get(baseId).push({ code, detailId, sourceImageUrl });
    });

    const out = [];
    for (const [baseId, variants] of byBase) {
        variants.sort((a, b) => {
            if (a.code === b.code) return 0;
            if (a.code === '') return -1;
            if (b.code === '') return 1;
            return a.code.localeCompare(b.code, undefined, { numeric: true });
        });
        out.push({ baseId, variants });
    }
    return out;
}

/**
 * Discover every variant image Bandai has for a single card id.
 *
 * Uses the freeword search (same POST endpoint as set listings) and
 * filters to entries whose detailId is exactly `cardId` or `cardId_pN`.
 * Substring matches on other cards (e.g. `ST01-001` matching `ST01-0010`)
 * are dropped.
 *
 * Returns the same shape as discoverSetCards()[i].variants:
 *   [{ code, detailId, sourceImageUrl }]
 */
async function discoverCardVariants(cardId) {
    const id = String(cardId).trim();
    if (!id) return [];

    const html = await fetchHtml(INDEX_URL, {
        method: 'POST',
        body: `freeword=${encodeURIComponent(id)}`,
    });

    const $ = cheerio.load(html);
    const variants = [];
    const seen = new Set();

    $('.cardItem').each((_, el) => {
        const $el = $(el);
        const a = $el.find('a').first();
        const detailSrc = a.attr('data-src') || a.attr('href') || '';
        const m = detailSrc.match(/detailSearch=([A-Z0-9_-]+)/i);
        if (!m) return;
        const detailId = m[1];

        const varMatch = detailId.match(/^(.+?)_p(\d+)$/i);
        const baseId = varMatch ? varMatch[1] : detailId;
        if (baseId !== id) return; // freeword can substring-match other cards

        if (seen.has(detailId)) return;
        seen.add(detailId);

        const img = $el.find('img').first();
        const rawImg = img.attr('data-src') || img.attr('src') || '';
        if (!rawImg || rawImg.includes('/parts/')) return;

        variants.push({
            code: varMatch ? `p${varMatch[2]}` : '',
            detailId,
            sourceImageUrl: new URL(rawImg, INDEX_URL).toString(),
        });
    });

    variants.sort((a, b) => {
        if (a.code === b.code) return 0;
        if (a.code === '') return -1;
        if (b.code === '') return 1;
        return a.code.localeCompare(b.code, undefined, { numeric: true });
    });
    return variants;
}

module.exports = {
    discoverSets,
    resolveSet,
    discoverSetCards,
    discoverCardVariants,
    INDEX_URL,
};
