#!/usr/bin/env node
// Regenerate EverShop sitemaps (sitemap-products.xml etc.) on demand.
// Run from store/ with the usual DB_* env vars:
//   cd store && DB_HOST=... DB_NAME=evershop node ../scripts/regen_sitemap.js
// The store's cron also regenerates every 30 minutes; this is for right-after-seeding.
import { createRequire } from 'module';
import { fileURLToPath, pathToFileURL } from 'url';
import path from 'path';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const storeRoot = path.resolve(scriptDir, '..', 'store');
const dist = (p) => pathToFileURL(path.join(storeRoot, 'packages/evershop/dist', p)).href;
const require = createRequire(path.join(storeRoot, 'package.json'));
require('config'); // load node-config from store/ (cwd must be store/)

const { generateSitemap } = await import(dist('modules/base/services/sitemap/generateSitemap.js'));
const { getBuiltinSitemapCollectors } = await import(dist('modules/base/services/sitemap/collectors/builtins.js'));
await generateSitemap({ collectors: getBuiltinSitemapCollectors(), force: true });
console.log('[regen_sitemap] done');
process.exit(0);
