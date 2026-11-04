const { supabase } = require('./supabase');
const { fetchCard } = require('./bandai');
const { rehostImage } = require('./images');
const { discoverCardVariants } = require('./discover');

/**
 * Scrape one card end-to-end: pull the detail page, rehost the base image,
 * rehost every alt-art variant, and upsert the row.
 *
 * Params:
 *   cardId      — base card id, e.g. "GD01-001"
 *   variants    — optional [{ code, sourceImageUrl }] from discoverSetCards().
 *                 If omitted (and `cardId` is given), we freeword-search
 *                 Bandai for this card's variants so a one-shot call
 *                 produces the same complete row as the bulk backfill.
 *   discoverVariants — pass `false` to skip auto-discovery when `variants`
 *                 is empty (used by the bulk backfill to avoid an extra
 *                 request per card when variants were already discovered
 *                 at the set level).
 *
 * Returns: { card, imageWarning, variantWarnings }
 */
async function scrapeCard({ cardId, url, variants = [], discoverVariants = true }) {
    const { row, sourceImageUrl } = await fetchCard({ cardId, url });

    const baseId = row.id;

    if (variants.length === 0 && discoverVariants && baseId) {
        try {
            variants = await discoverCardVariants(baseId);
        } catch (e) {
            // Non-fatal: fall through with just the base image.
            console.warn(`[scrape] variant discovery failed for ${baseId}: ${e.message}`);
            variants = [];
        }
    }

    // ---- Base image ----
    let imageWarning = null;
    const baseSource =
        variants.find((v) => v.code === '')?.sourceImageUrl || sourceImageUrl;

    if (baseSource) {
        try {
            const { publicUrl } = await rehostImage({
                sourceUrl: baseSource,
                cardId: baseId,
            });
            row.image_url = publicUrl;
            row.text_data.source_image_url = baseSource;
        } catch (e) {
            imageWarning = e.message;
        }
    }

    // ---- Alt-art variants ----
    const altVariants = variants.filter((v) => v.code && v.code !== '');
    const variantRecords = [];
    const variantWarnings = [];
    for (const v of altVariants) {
        const storageName = `${baseId}_${v.code}`;
        try {
            const { publicUrl } = await rehostImage({
                sourceUrl: v.sourceImageUrl,
                storageName,
            });
            variantRecords.push({
                code: v.code,
                image_url: publicUrl,
                source_image_url: v.sourceImageUrl,
            });
        } catch (e) {
            variantWarnings.push({ code: v.code, error: e.message });
        }
    }
    if (variantRecords.length > 0) {
        row.text_data.variants = variantRecords;
    }

    // ---- Upsert ----
    const { data, error } = await supabase
        .from('cards')
        .upsert(row, { onConflict: 'id' })
        .select()
        .single();
    if (error) {
        const err = new Error(`Supabase upsert failed: ${error.message}`);
        err.status = 502;
        throw err;
    }

    return { card: data, imageWarning, variantWarnings };
}

module.exports = { scrapeCard };
