const path = require('path');
const axios = require('axios');

const { supabase } = require('./supabase');
const { IMAGE_HEADERS: BROWSER_HEADERS } = require('./http');

const BUCKET = process.env.SUPABASE_IMAGE_BUCKET || 'card-images';

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
 * Download the image at `sourceUrl` with browser headers and upload it to
 * the public Supabase Storage bucket. By default the object lands at
 * `cards/<cardId>.<ext>`; pass `storageName` to override (used by variants
 * like `<baseId>_p1`). Throws on any failure — the caller decides whether a
 * missing image should fail the whole request.
 */
async function rehostImage({ sourceUrl, cardId, storageName }) {
    if (!sourceUrl) throw new Error('rehostImage: sourceUrl is required');
    const name = (storageName || cardId || '').trim();
    if (!name) throw new Error('rehostImage: cardId or storageName is required');

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
    const objectPath = `cards/${name}.${ext}`;

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
