const path = require('path');
const axios = require('axios');

const { supabase } = require('./supabase');

const BUCKET = process.env.SUPABASE_IMAGE_BUCKET || 'card-images';

// Same UA trick as the HTML scraper — Bandai's CDN serves the images with
// the same 403 behavior as the card pages when it doesn't like the client.
const BROWSER_HEADERS = {
    'User-Agent':
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
        '(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
    Accept: 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    Referer: 'https://www.gundam-gcg.com/en/cards/',
};

const EXT_FROM_MIME = {
    'image/png': 'png',
    'image/jpeg': 'jpg',
    'image/jpg': 'jpg',
    'image/webp': 'webp',
    'image/gif': 'gif',
    'image/avif': 'avif',
};

function extFor(sourceUrl, contentType) {
    const fromMime = EXT_FROM_MIME[(contentType || '').split(';')[0].trim().toLowerCase()];
    if (fromMime) return fromMime;

    const pathname = (() => {
        try { return new URL(sourceUrl).pathname; } catch { return ''; }
    })();
    const ext = path.extname(pathname).replace('.', '').toLowerCase();
    return ext || 'png';
}

/**
 * Download the image at `sourceUrl` with browser headers, upload it to the
 * public Supabase Storage bucket under `cards/<cardId>.<ext>`, and return
 * its public URL. Throws on any failure — the caller decides whether a
 * missing image should fail the whole request.
 */
async function rehostImage({ sourceUrl, cardId }) {
    if (!sourceUrl) throw new Error('rehostImage: sourceUrl is required');
    if (!cardId) throw new Error('rehostImage: cardId is required');

    const res = await axios.get(sourceUrl, {
        headers: BROWSER_HEADERS,
        timeout: 20_000,
        maxRedirects: 5,
        responseType: 'arraybuffer',
        // Guard against pathological payloads (10 MB is way more than any card art).
        maxContentLength: 10 * 1024 * 1024,
        validateStatus: (s) => s >= 200 && s < 400,
    });

    const contentType = (res.headers['content-type'] || 'image/png').split(';')[0].trim();
    const ext = extFor(sourceUrl, contentType);
    const objectPath = `cards/${cardId}.${ext}`;

    const { error: uploadError } = await supabase.storage
        .from(BUCKET)
        .upload(objectPath, Buffer.from(res.data), {
            contentType,
            upsert: true,
            cacheControl: '31536000', // 1 year — card art is immutable per serial.
        });

    if (uploadError) {
        throw new Error(`Supabase Storage upload failed: ${uploadError.message}`);
    }

    const { data } = supabase.storage.from(BUCKET).getPublicUrl(objectPath);
    return { publicUrl: data.publicUrl, objectPath, contentType, bytes: res.data.length };
}

module.exports = { rehostImage, BUCKET };
