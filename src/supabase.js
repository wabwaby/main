const { createClient } = require('@supabase/supabase-js');

const { SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY } = process.env;

if (!SUPABASE_URL || !SUPABASE_SERVICE_ROLE_KEY) {
    // Fail loudly at boot rather than silently 500ing on the first request.
    throw new Error(
        'Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY. ' +
            'Copy .env.example to .env and fill them in.',
    );
}

// Service-role client: bypasses RLS. Keep this process-local — do not expose
// the key or this client to the browser.
const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, {
    auth: { persistSession: false, autoRefreshToken: false },
});

module.exports = { supabase };
