require('dotenv').config();

const express = require('express');
const cors = require('cors');

const { supabase } = require('./supabase');
const { fetchCard } = require('./bandai');

const app = express();
app.use(express.json({ limit: '64kb' }));

const allowedOrigins = (process.env.ALLOWED_ORIGINS || '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);

app.use(
    cors({
        origin: (origin, cb) => {
            // Allow same-origin / curl / server-to-server (no Origin header).
            if (!origin) return cb(null, true);
            if (allowedOrigins.length === 0 || allowedOrigins.includes(origin)) {
                return cb(null, true);
            }
            return cb(new Error(`Origin ${origin} not allowed`));
        },
    }),
);

app.get('/healthz', (_req, res) => res.json({ ok: true }));

/**
 * POST /api/fetch-and-store-card
 *   body: { url?: string, cardId?: string }
 * GET  /api/fetch-and-store-card?url=...  or  ?cardId=ST01-001
 *
 * Fetches the card from Bandai (server-side, with a browser UA to dodge
 * their 403s), parses it, and upserts it into `public.cards`.
 */
async function handleFetchAndStore(req, res) {
    const url = req.body?.url || req.query.url;
    const cardId = req.body?.cardId || req.query.cardId;

    if (!url && !cardId) {
        return res.status(400).json({ error: 'Provide `url` or `cardId`.' });
    }

    try {
        const card = await fetchCard({ url, cardId });

        const { data, error } = await supabase
            .from('cards')
            .upsert(card, { onConflict: 'id' })
            .select()
            .single();

        if (error) {
            console.error('[supabase] upsert failed', error);
            return res.status(502).json({ error: 'Supabase upsert failed', detail: error.message });
        }

        return res.status(200).json({ card: data });
    } catch (err) {
        const status = err.status || (err.response?.status ?? 500);
        console.error('[fetch-and-store-card] failed', {
            status,
            message: err.message,
            url,
            cardId,
        });
        return res.status(status >= 400 && status < 600 ? status : 500).json({
            error: err.message || 'Unknown error',
        });
    }
}

app.get('/api/fetch-and-store-card', handleFetchAndStore);
app.post('/api/fetch-and-store-card', handleFetchAndStore);

// Catch-all 404 so the frontend gets JSON, not an HTML error page.
app.use((_req, res) => res.status(404).json({ error: 'Not found' }));

const port = Number(process.env.PORT) || 3001;
if (require.main === module) {
    app.listen(port, () => {
        console.log(`gundam-card-proxy listening on http://localhost:${port}`);
    });
}

module.exports = { app };
