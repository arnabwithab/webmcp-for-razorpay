#!/usr/bin/env node
// image-first: fetch one image per grocery SKU, then seed creates products from those images
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.resolve(scriptDir, '..', 'store/media/grocery');
if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });

// SKU -> loremflickr keyword (comma-separated, grocery-relevant)
const IMAGES = [
  ['GROC-S01', 'rice,basmati'],
  ['GROC-S02', 'rice,sack'],
  ['GROC-S03', 'flour,atta'],
  ['GROC-S04', 'flour,wheat'],
  ['GROC-S05', 'lentils,dal'],
  ['GROC-S06', 'lentils,moong'],
  ['GROC-S07', 'oil,mustard'],
  ['GROC-S08', 'oil,sunflower'],
  ['GROC-S09', 'sugar,white'],
  ['GROC-F01', 'mango,fruit'],
  ['GROC-F02', 'banana,fruit'],
  ['GROC-F03', 'tomato,vegetable'],
  ['GROC-F04', 'onion,vegetable'],
  ['GROC-F05', 'potato,vegetable'],
  ['GROC-F06', 'capsicum,vegetable'],
  ['GROC-F07', 'spinach,leafy'],
  ['GROC-F08', 'apple,fruit'],
  ['GROC-F09', 'carrot,vegetable'],
  ['GROC-D01', 'milk,dairy'],
  ['GROC-D02', 'curd,yogurt'],
  ['GROC-D03', 'paneer,cheese'],
  ['GROC-D04', 'bread,loaf'],
  ['GROC-D05', 'bread,brown'],
  ['GROC-D06', 'eggs,tray'],
  ['GROC-D07', 'eggs,carton'],
  ['GROC-D08', 'butter,dairy'],
  ['GROC-D09', 'cheese,slices'],
  ['GROC-B01', 'tea,leaves'],
  ['GROC-B02', 'coffee,jar'],
  ['GROC-B03', 'orange,juice'],
  ['GROC-B04', 'mango,juice'],
  ['GROC-B05', 'water,bottle'],
  ['GROC-B06', 'cola,softdrink'],
  ['GROC-B07', 'coconut,water'],
  ['GROC-B08', 'greentea,teabag'],
  ['GROC-H01', 'chips,potato'],
  ['GROC-H02', 'chips,packet'],
  ['GROC-H03', 'peanuts,roasted'],
  ['GROC-H04', 'biscuits,packet'],
  ['GROC-H05', 'noodles,instant'],
  ['GROC-H06', 'dishsoap,kitchen'],
  ['GROC-H07', 'detergent,powder'],
  ['GROC-H08', 'garbage,bag'],
  ['GROC-H09', 'tissue,kitchen'],
  ['GROC-H10', 'salt,packet'],
  ['GROC-S10', 'salt,rock'],
  ['GROC-F10', 'lemon,fruit'],
];

async function fetchOne(sku, keyword, idx, retries = 3) {
  const out = path.join(outDir, `${sku}-1.jpg`);
  if (fs.existsSync(out) && fs.statSync(out).size > 5000) {
    console.log(`[fetch] skip ${sku} exists`);
    return true;
  }
  const url = `https://loremflickr.com/800/800/${keyword}?lock=${idx + 101}`;
  for (let attempt = 1; attempt <= retries; attempt++) {
    try {
      const res = await fetch(url, { redirect: 'follow' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const buf = Buffer.from(await res.arrayBuffer());
      if (buf.length < 5000) throw new Error(`too small ${buf.length}`);
      // basic jpeg check
      if (buf[0] !== 0xff || buf[1] !== 0xd8) throw new Error('not jpeg');
      fs.writeFileSync(out, buf);
      console.log(`[fetch] ${sku} ${keyword} -> ${buf.length} bytes`);
      return true;
    } catch (e) {
      console.warn(`[fetch] ${sku} attempt ${attempt} failed: ${e.message}`);
      if (attempt < retries) await new Promise((r) => setTimeout(r, 800 * attempt));
    }
  }
  // fallback to picsum if loremflickr fails
  try {
    const res = await fetch(`https://picsum.photos/seed/${sku}/800/800`);
    const buf = Buffer.from(await res.arrayBuffer());
    fs.writeFileSync(out, buf);
    console.log(`[fetch] ${sku} fallback picsum ${buf.length}`);
    return true;
  } catch (e) {
    console.error(`[fetch] ${sku} FAILED both sources: ${e.message}`);
    return false;
  }
}

async function main() {
  let ok = 0;
  for (let i = 0; i < IMAGES.length; i++) {
    const [sku, kw] = IMAGES[i];
    const res = await fetchOne(sku, kw, i);
    if (res) ok++;
    if (i < IMAGES.length - 1) await new Promise((r) => setTimeout(r, 350));
  }
  console.log(`[fetch] done ${ok}/${IMAGES.length}`);
  if (ok < IMAGES.length) {
    console.error(`[fetch] missing ${IMAGES.length - ok} images`);
    process.exit(1);
  }
}

main().catch((e) => { console.error(e); process.exit(1); });
