#!/usr/bin/env node
/* eslint-disable no-console */
require('dotenv').config();

const { discoverSets, resolveSet, discoverSetCards } = require('../src/discover');
const { scrapeCard } = require('../src/scrape');
const { supabase } = require('../src/supabase');

function parseArgs(argv) {
    const out = {
        sets: [],
        cards: [],
        all: false,
        concurrency: 3,
        delayMs: 250,
        dryRun: false,
        skipExisting: false,
        help: false,
    };
    const rest = [];
    for (let i = 0; i < argv.length; i++) {
        const a = argv[i];
        if (a === '--all' || a === '-a') out.all = true;
        else if (a === '--set' || a === '-s') out.sets.push(argv[++i]);
        else if (a === '--card' || a === '-c') out.cards.push(argv[++i]);
        else if (a === '--concurrency') out.concurrency = Number(argv[++i]);
        else if (a === '--delay') out.delayMs = Number(argv[++i]);
        else if (a === '--dry-run') out.dryRun = true;
        else if (a === '--skip-existing') out.skipExisting = true;
        else if (a === '--help' || a === '-h') out.help = true;
        else rest.push(a);
    }
    for (const r of rest) {
        if (/^[A-Z0-9]+-[A-Z0-9]+$/i.test(r)) out.cards.push(r);
        else if (r) out.sets.push(r);
    }
    return out;
}

function printHelp() {
    console.log(`
gundam-card-proxy backfill

  Scrapes Bandai's card catalog into Supabase. Future-proof: discovers
  sets automatically, so new sets and SP reprints are picked up on each
  re-run.

Usage:
  node scripts/backfill.js [options] [sets...] [card-ids...]

Options:
  --all, -a              Scrape every set Bandai currently exposes
  --set, -s CODE         Scrape one set (e.g. ST01, GD01, or internal id 616001).
                         May be repeated.
  --card, -c ID          Scrape one specific card (e.g. ST01-001). May be repeated.
  --concurrency N        How many cards to process in parallel (default 3).
  --delay MS             Min delay between card requests per worker (default 250).
  --skip-existing        Skip cards that already have a row in public.cards
                         (fast resume; new alt arts for existing cards get missed).
  --dry-run              List what would be scraped, don't hit the DB or rehost.
  --help, -h             Show this message.

Examples:
  node scripts/backfill.js --all
  node scripts/backfill.js --set ST01 --set ST02
  node scripts/backfill.js ST01-001 ST01-007
  node scripts/backfill.js --set 'Promotion card' --concurrency 5
`);
}

function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
}

async function pLimitMap(items, limit, fn) {
    const results = new Array(items.length);
    let cursor = 0;
    const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
        while (true) {
            const i = cursor++;
            if (i >= items.length) return;
            results[i] = await fn(items[i], i);
        }
    });
    await Promise.all(workers);
    return results;
}

async function listExistingIds() {
    const { data, error } = await supabase.from('cards').select('id');
    if (error) throw new Error(`Supabase select failed: ${error.message}`);
    return new Set(data.map((r) => r.id));
}

async function main() {
    const opts = parseArgs(process.argv.slice(2));
    if (opts.help) {
        printHelp();
        return;
    }

    const explicitSets = opts.sets.length > 0;
    const explicitCards = opts.cards.length > 0;
    const wantAll = opts.all || (!explicitSets && !explicitCards);

    console.log('Discovering sets from gundam-gcg.com …');
    const allSets = await discoverSets();
    console.log(`  found ${allSets.length} sets.`);

    let targetSets = [];
    if (explicitSets) {
        for (const hint of opts.sets) {
            targetSets.push(await resolveSet(hint, allSets));
        }
    } else if (wantAll) {
        targetSets = allSets;
    }

    console.log(`\nTargets:`);
    if (targetSets.length) {
        for (const s of targetSets) console.log(`  set  ${s.code || '----'}  (${s.internalId})  ${s.displayName}`);
    }
    if (explicitCards) {
        for (const c of opts.cards) console.log(`  card ${c}`);
    }

    // Flatten targets → one scrape unit per base card.
    const units = new Map(); // key: baseId, value: variants[]
    for (const set of targetSets) {
        process.stdout.write(`\nListing ${set.code || set.internalId} …`);
        const cards = await discoverSetCards(set.internalId);
        process.stdout.write(` ${cards.length} base cards\n`);
        for (const c of cards) {
            if (!units.has(c.baseId)) units.set(c.baseId, c.variants);
            else {
                const existing = units.get(c.baseId);
                const seen = new Set(existing.map((v) => v.code));
                for (const v of c.variants) if (!seen.has(v.code)) existing.push(v);
            }
        }
    }
    for (const id of opts.cards) {
        if (!units.has(id)) units.set(id, []); // detail page will supply the base image
    }

    const allUnits = [...units.entries()].map(([baseId, variants]) => ({ baseId, variants }));
    console.log(`\nTotal unique cards to scrape: ${allUnits.length}`);

    if (opts.skipExisting) {
        const existing = await listExistingIds();
        const before = allUnits.length;
        for (let i = allUnits.length - 1; i >= 0; i--) {
            if (existing.has(allUnits[i].baseId)) allUnits.splice(i, 1);
        }
        console.log(`  --skip-existing: dropped ${before - allUnits.length} already in DB.`);
    }

    if (opts.dryRun) {
        console.log('\n--dry-run: not calling scrapeCard.');
        for (const u of allUnits.slice(0, 20)) {
            console.log(`  ${u.baseId}  (variants: ${u.variants.length})`);
        }
        if (allUnits.length > 20) console.log(`  … and ${allUnits.length - 20} more`);
        return;
    }

    console.log(`\nScraping with concurrency=${opts.concurrency}, delay=${opts.delayMs}ms per worker.\n`);

    const started = Date.now();
    let done = 0;
    const failures = [];
    const imageIssues = [];

    await pLimitMap(allUnits, opts.concurrency, async (u) => {
        try {
            await sleep(opts.delayMs);
            // Always auto-discover variants per card. The set-listing shows
            // all base ids but sometimes under-reports variants; a freeword
            // lookup catches `_pN` arts the set page misses.
            const res = await scrapeCard({ cardId: u.baseId });
            done++;
            const variantCount = res.card.text_data?.variants?.length || 0;
            const warnBits = [];
            if (res.imageWarning) warnBits.push(`base:${res.imageWarning}`);
            if (res.variantWarnings?.length) warnBits.push(`${res.variantWarnings.length} variant(s) failed`);
            const warnStr = warnBits.length ? `  ⚠ ${warnBits.join(' | ')}` : '';
            console.log(
                `  [${done}/${allUnits.length}] ${u.baseId}  "${res.card.card_name}"  variants=${variantCount}${warnStr}`,
            );
            if (res.imageWarning) imageIssues.push({ baseId: u.baseId, kind: 'base', error: res.imageWarning });
            for (const vw of res.variantWarnings || []) {
                imageIssues.push({ baseId: u.baseId, kind: `variant:${vw.code}`, error: vw.error });
            }
        } catch (e) {
            done++;
            failures.push({ baseId: u.baseId, error: e.message });
            console.log(`  [${done}/${allUnits.length}] ${u.baseId}  ✗ ${e.message}`);
        }
    });

    const secs = ((Date.now() - started) / 1000).toFixed(1);
    console.log(`\nDone in ${secs}s.`);
    console.log(`  succeeded: ${allUnits.length - failures.length}/${allUnits.length}`);
    if (failures.length) {
        console.log(`  failures (${failures.length}):`);
        for (const f of failures.slice(0, 20)) console.log(`    ${f.baseId}  ${f.error}`);
        if (failures.length > 20) console.log(`    … and ${failures.length - 20} more`);
    }
    if (imageIssues.length) {
        console.log(`  image issues (${imageIssues.length}): first 10:`);
        for (const w of imageIssues.slice(0, 10)) console.log(`    ${w.baseId} ${w.kind}  ${w.error}`);
    }
    if (failures.length) process.exit(1);
}

main().catch((e) => {
    console.error('\nBackfill crashed:', e);
    process.exit(2);
});
