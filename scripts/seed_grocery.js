#!/usr/bin/env node
// Grocery catalog seed for the EverShop demo store (hackathon).
// Wipes demo catalog data, then inserts 5 categories + 47 INR grocery products
// with local images (store/media/grocery/*) and a `homepage` featured collection.
//
// Image-first flow: every SKU has a corresponding store/media/grocery/<SKU>-1.jpg
// fetched by scripts/fetch_grocery_images.js before this seed runs.
//
// Run from store/ so node-config + node_modules resolve:
//   cd store
//   DB_HOST=localhost DB_PORT=5432 DB_USER=postgres DB_PASSWORD=evershop DB_NAME=evershop \
//     node ../scripts/seed_grocery.js
//
// Uses the EverShop service layer for inserts. Deletes are raw SQL (FKs cascade).
import { createRequire } from 'module';
import { fileURLToPath, pathToFileURL } from 'url';
import path from 'path';
import fs from 'fs';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const storeRoot = path.resolve(scriptDir, '..', 'store');
if (!fs.existsSync(path.join(storeRoot, 'package.json'))) {
  console.error('ERROR: store/ not found next to scripts/. Run: cd store && node ../scripts/seed_grocery.js');
  process.exit(1);
}
const dist = (p) => pathToFileURL(path.join(storeRoot, 'packages/evershop/dist', p)).href;
const require = createRequire(path.join(storeRoot, 'package.json'));
const { Pool } = require('pg');

const log = (m) => console.log(`[seed_grocery] ${m}`);
const die = (m) => { console.error(`[seed_grocery] ERROR: ${m}`); process.exit(1); };

// ---------------------------------------------------------------------------
// Catalog data (INR pricing) - grocery/essentials, 47 SKUs
// Variant handling: A - simple products per pack (e.g. Rice 1kg vs 5kg are distinct SKUs)
// 4 deliberately OOS SKUs for demo: GROC-S09, GROC-F03, GROC-D08, GROC-H07
// ---------------------------------------------------------------------------
const CATEGORIES = [
  {
    name: 'Staples', url_key: 'staples',
    meta_title: 'Staples - Rice, Atta, Dal, Oil & Salt',
    meta_description: 'Daily staples - basmati rice, whole wheat atta, toor and moong dal, cold-pressed oils and salts. Pantry essentials at kirana prices.',
    meta_keywords: 'rice, atta, dal, oil, sugar, salt, staples, grocery',
    copy: ['Your kirana shelf, stocked right - rice that stays fluffy, atta that stays soft, dal that cooks in one whistle.', 'Staples sourced for everyday Indian cooking - honest weights, honest prices, zero surprises.']
  },
  {
    name: 'Fresh Produce', url_key: 'fresh',
    meta_title: 'Fresh Produce - Fruits & Vegetables',
    meta_description: 'Farm-fresh fruits and vegetables - mangoes, bananas, apples, tomatoes, onions, potatoes, capsicum and leafy greens.',
    meta_keywords: 'fresh produce, fruits, vegetables, mango, tomato, onion, potato',
    copy: ['Picked this morning, on your shelf by evening - farm-fresh produce with no cold-chain breaks.', 'Seasonal fruits and daily vegetables, graded and packed for real Indian kitchens.']
  },
  {
    name: 'Dairy & Bakery', url_key: 'dairy',
    meta_title: 'Dairy & Bakery - Milk, Curd, Paneer, Bread & Eggs',
    meta_description: 'Dairy and bakery - full-cream milk, curd, paneer, white and brown bread, farm eggs, butter and cheese.',
    meta_keywords: 'dairy, milk, curd, paneer, bread, eggs, butter, cheese',
    copy: ['From the dairy to your door - milk, curd and paneer with same-day freshness, plus bakery bread baked overnight.', 'Protein for every meal - eggs, paneer and cheese for growing families and busy mornings.']
  },
  {
    name: 'Beverages', url_key: 'beverages',
    meta_title: 'Beverages - Tea, Coffee, Juices & Water',
    meta_description: 'Beverages - Darjeeling tea, instant coffee, orange and mango juices, mineral water, cola and coconut water.',
    meta_keywords: 'beverages, tea, coffee, juice, water, cola, coconut water',
    copy: ['Sip, refresh, repeat - chai, coffee, juices and water for every mood of the day.', 'From morning chai to late-night cola, beverages that keep households running.']
  },
  {
    name: 'Snacks & Household', url_key: 'snacks',
    meta_title: 'Snacks & Household - Chips, Biscuits, Noodles & Essentials',
    meta_description: 'Snacks and household - potato chips, peanuts, biscuits, instant noodles, dish soap, detergent and tissues.',
    meta_keywords: 'snacks, chips, biscuits, noodles, household, detergent, dish soap',
    copy: ['Evening cravings and daily chores - snacks for the kids, essentials for the kitchen.', 'One cart for both indulgence and upkeep - from chips to detergent.']
  }
];

// image paths are under store/media/grocery/ -> served at /assets/grocery/...
const PRODUCTS = [
  // ---- Staples (11) ----
  {
    sku: 'GROC-S01', name: 'Basmati Rice 1kg', category: 'staples', price: 299, weight: 1.0, qty: 40, featured: true,
    description: 'Aged basmati with extra-long grains that stay separate and fluffy after cooking. Ideal for pulao, biryani and daily rice.',
    meta_description: 'Aged basmati rice 1kg - extra-long grains, fluffy and aromatic.'
  },
  {
    sku: 'GROC-S02', name: 'Basmati Rice 5kg', category: 'staples', price: 1299, weight: 5.0, qty: 20, featured: true,
    description: 'Family pack of the same aged basmati - 5kg sack with better per-kilo value. Same aroma, bulk savings.',
    meta_description: 'Basmati rice 5kg family pack - aged, aromatic, bulk value.'
  },
  {
    sku: 'GROC-S03', name: 'Whole Wheat Atta 5kg', category: 'staples', price: 349, weight: 5.0, qty: 40,
    description: 'Chakki-ground whole wheat atta - soft rotis that puff without extra ghee. High fibre, no maida mixing.',
    meta_description: 'Whole wheat atta 5kg - chakki-ground, soft rotis.'
  },
  {
    sku: 'GROC-S04', name: 'Whole Wheat Atta 10kg', category: 'staples', price: 649, weight: 10.0, qty: 25,
    description: '10kg atta for joint families - same chakki grind, heavier sack for fortnightly stock-ups.',
    meta_description: 'Whole wheat atta 10kg - bulk sack for families.'
  },
  {
    sku: 'GROC-S05', name: 'Toor Dal 1kg', category: 'staples', price: 189, weight: 1.0, qty: 40, featured: true,
    description: 'Polished toor dal that cooks to a creamy dal in one whistle. Clean, stone-free and protein-rich.',
    meta_description: 'Toor dal 1kg - polished, stone-free, one-whistle cook.'
  },
  {
    sku: 'GROC-S06', name: 'Moong Dal 1kg', category: 'staples', price: 169, weight: 1.0, qty: 40,
    description: 'Split yellow moong dal - light on the stomach, quick to cook, perfect for khichdi and soups.',
    meta_description: 'Moong dal 1kg - split yellow, quick-cook khichdi dal.'
  },
  {
    sku: 'GROC-S07', name: 'Cold-Pressed Mustard Oil 1L', category: 'staples', price: 349, weight: 0.9, qty: 30,
    description: 'Kachi ghani mustard oil with pungent aroma - traditional tadka oil for pickles and curries.',
    meta_description: 'Mustard oil 1L kachi ghani - pungent, traditional.'
  },
  {
    sku: 'GROC-S08', name: 'Sunflower Oil 1L', category: 'staples', price: 199, weight: 0.9, qty: 30,
    description: 'Refined sunflower oil - light, neutral and high-smoke for daily frying and sauteing.',
    meta_description: 'Sunflower oil 1L refined - light, high-smoke.'
  },
  {
    sku: 'GROC-S09', name: 'White Sugar 1kg', category: 'staples', price: 59, weight: 1.0, qty: 0, stock_availability: false,
    description: 'Fine white sugar - dissolves clean in chai and desserts. Currently out of stock due to high demand.',
    meta_description: 'White sugar 1kg - fine, fast-dissolving. Out of stock.'
  },
  {
    sku: 'GROC-S10', name: 'Rock Salt 1kg', category: 'staples', price: 89, weight: 1.0, qty: 40,
    description: 'Sendha rock salt - coarsely ground, ideal for fasting recipes and healthier seasoning.',
    meta_description: 'Rock salt 1kg sendha - for fasting and daily use.'
  },
  {
    sku: 'GROC-H10', name: 'Table Salt 1kg', category: 'staples', price: 29, weight: 1.0, qty: 50,
    description: 'Iodized table salt - fine grains, free-flow with anti-caking. The everyday salt for every kitchen.',
    meta_description: 'Iodized table salt 1kg - fine, free-flow.'
  },
  // ---- Fresh Produce (10) ----
  {
    sku: 'GROC-F01', name: 'Alphonso Mangoes 1kg', category: 'fresh', price: 399, weight: 1.0, qty: 25, featured: true,
    description: 'Ratnagiri alphonso mangoes - naturally ripened, saffron pulp with honeyed aroma. Seasonal, limited stock.',
    meta_description: 'Alphonso mangoes 1kg Ratnagiri - naturally ripened, seasonal.'
  },
  {
    sku: 'GROC-F02', name: 'Bananas Robusta 1kg', category: 'fresh', price: 59, weight: 1.0, qty: 50,
    description: 'Robusta bananas - firm, sweet and energy-dense. Perfect for breakfast, smoothies and kids tiffin.',
    meta_description: 'Robusta bananas 1kg - sweet, firm, tiffin-ready.'
  },
  {
    sku: 'GROC-F03', name: 'Fresh Tomatoes 1kg', category: 'fresh', price: 49, weight: 1.0, qty: 0, stock_availability: false,
    description: 'Vine-ripened tomatoes - tangy and firm for curries and salads. Temporarily out of stock due to mandi delay.',
    meta_description: 'Fresh tomatoes 1kg - vine-ripened. Out of stock.'
  },
  {
    sku: 'GROC-F04', name: 'Onions 2kg', category: 'fresh', price: 89, weight: 2.0, qty: 40,
    description: 'Nashik onions 2kg pack - pungent, long shelf-life, the base of every Indian gravy.',
    meta_description: 'Nashik onions 2kg - pungent, long shelf-life.'
  },
  {
    sku: 'GROC-F05', name: 'Baby Potatoes 1kg', category: 'fresh', price: 39, weight: 1.0, qty: 50,
    description: 'Small baby potatoes - thin skin, quick-boil, perfect for dum aloo and salads.',
    meta_description: 'Baby potatoes 1kg - thin skin, quick-boil.'
  },
  {
    sku: 'GROC-F06', name: 'Green Capsicum 500g', category: 'fresh', price: 79, weight: 0.5, qty: 30,
    description: 'Crisp green capsicum 500g - glossy, seedless, adds crunch to noodles and curries.',
    meta_description: 'Green capsicum 500g - crisp, glossy, seedless.'
  },
  {
    sku: 'GROC-F07', name: 'Fresh Spinach Bunch', category: 'fresh', price: 35, weight: 0.25, qty: 30,
    description: 'Tender spinach bunch - washed, shade-grown, iron-rich for saag and smoothies.',
    meta_description: 'Fresh spinach bunch - washed, tender, iron-rich.'
  },
  {
    sku: 'GROC-F08', name: 'Shimla Apples 1kg', category: 'fresh', price: 199, weight: 1.0, qty: 30, featured: true,
    description: 'Shimla apples - crisp, sweet-tart and wax-free. Hand-graded for size and shine.',
    meta_description: 'Shimla apples 1kg - crisp, wax-free, hand-graded.'
  },
  {
    sku: 'GROC-F09', name: 'Carrots 500g', category: 'fresh', price: 45, weight: 0.5, qty: 35,
    description: 'Ooty carrots 500g - sweet, crunchy and bright orange. Great for halwa, salads and juice.',
    meta_description: 'Ooty carrots 500g - sweet, crunchy.'
  },
  {
    sku: 'GROC-F10', name: 'Lemons 500g', category: 'fresh', price: 49, weight: 0.5, qty: 40,
    description: 'Seedless lemons 500g - juicy with thin rind, ideal for shikanji and garnish.',
    meta_description: 'Seedless lemons 500g - juicy, thin rind.'
  },
  // ---- Dairy & Bakery (9) ----
  {
    sku: 'GROC-D01', name: 'Full-Cream Milk 1L', category: 'dairy', price: 68, weight: 1.0, qty: 50,
    description: 'Full-cream toned milk 1L - pasteurized, 6% fat, same-day dairy. Boil and use within 2 days.',
    meta_description: 'Full-cream milk 1L - pasteurized, 6% fat.'
  },
  {
    sku: 'GROC-D02', name: 'Curd Cup 400g', category: 'dairy', price: 45, weight: 0.4, qty: 40,
    description: 'Set curd 400g - thick, not sour, made from toned milk. Perfect for raita and curd rice.',
    meta_description: 'Set curd 400g - thick, toned milk.'
  },
  {
    sku: 'GROC-D03', name: 'Paneer 200g', category: 'dairy', price: 89, weight: 0.2, qty: 30, featured: true,
    description: 'Soft malai paneer 200g - pressed fresh, cubes hold shape in curry and grill.',
    meta_description: 'Malai paneer 200g - soft, cube-ready.'
  },
  {
    sku: 'GROC-D04', name: 'White Bread 400g', category: 'dairy', price: 45, weight: 0.4, qty: 40,
    description: 'Soft white bread 400g - sliced, pillowy, baked overnight for morning toast and sandwiches.',
    meta_description: 'White bread 400g sliced - soft, overnight baked.'
  },
  {
    sku: 'GROC-D05', name: 'Brown Bread 400g', category: 'dairy', price: 55, weight: 0.4, qty: 35,
    description: 'Brown bread 400g - whole wheat blend, fibre-rich, lightly sweet for healthier toast.',
    meta_description: 'Brown bread 400g whole wheat - fibre-rich.'
  },
  {
    sku: 'GROC-D06', name: 'Farm Eggs 30 pcs', category: 'dairy', price: 199, weight: 1.8, qty: 25, featured: true,
    description: 'Farm eggs 30-piece tray - white, protein-rich, candled and graded for size.',
    meta_description: 'Farm eggs 30 pcs tray - white, graded.'
  },
  {
    sku: 'GROC-D07', name: 'Farm Eggs 6 pcs', category: 'dairy', price: 49, weight: 0.36, qty: 50,
    description: 'Farm eggs 6-piece pack - same graded eggs, small pack for weekly top-ups.',
    meta_description: 'Farm eggs 6 pcs - small pack, graded.'
  },
  {
    sku: 'GROC-D08', name: 'Butter 100g', category: 'dairy', price: 59, weight: 0.1, qty: 0, stock_availability: false,
    description: 'Salted butter 100g - creamy, easy-spread. Out of stock - cold-chain restock tomorrow.',
    meta_description: 'Salted butter 100g - creamy. Out of stock.'
  },
  {
    sku: 'GROC-D09', name: 'Cheese Slices 200g', category: 'dairy', price: 149, weight: 0.2, qty: 25,
    description: 'Cheddar cheese slices 200g - 10 individually wrapped slices, melt-ready for burgers and toasties.',
    meta_description: 'Cheddar cheese slices 200g - 10 slices, melt-ready.'
  },
  // ---- Beverages (8) ----
  {
    sku: 'GROC-B01', name: 'Darjeeling Tea 250g', category: 'beverages', price: 299, weight: 0.25, qty: 30, featured: true,
    description: 'Second-flush Darjeeling tea 250g - floral aroma, muscatel finish. Single-estate leaves.',
    meta_description: 'Darjeeling tea 250g second-flush - floral, muscatel.'
  },
  {
    sku: 'GROC-B02', name: 'Instant Coffee 100g', category: 'beverages', price: 249, weight: 0.1, qty: 30,
    description: 'Instant coffee 100g - strong, aromatic, dissolves in hot water or milk in seconds.',
    meta_description: 'Instant coffee 100g - strong, quick-dissolve.'
  },
  {
    sku: 'GROC-B03', name: 'Orange Juice 1L', category: 'beverages', price: 129, weight: 1.0, qty: 25,
    description: 'Cold-pressed orange juice 1L - no added sugar, pulpy and vitamin-C rich.',
    meta_description: 'Orange juice 1L cold-pressed - no added sugar.'
  },
  {
    sku: 'GROC-B04', name: 'Mango Juice 1L', category: 'beverages', price: 119, weight: 1.0, qty: 25,
    description: 'Alphonso mango juice 1L - thick, sweet and summer-ready. Shake well before pouring.',
    meta_description: 'Mango juice 1L alphonso - thick, sweet.'
  },
  {
    sku: 'GROC-B05', name: 'Mineral Water 1L x6', category: 'beverages', price: 149, weight: 6.0, qty: 30,
    description: 'Mineral water 1L six-pack - sealed, TDS-balanced, weekly hydration for families.',
    meta_description: 'Mineral water 1L six-pack - sealed, TDS-balanced.'
  },
  {
    sku: 'GROC-B06', name: 'Cola 2L', category: 'beverages', price: 99, weight: 2.0, qty: 30,
    description: 'Cola 2L PET - fizzy, chilled-best, party-size for gatherings.',
    meta_description: 'Cola 2L PET - fizzy, party-size.'
  },
  {
    sku: 'GROC-B07', name: 'Coconut Water 350ml', category: 'beverages', price: 45, weight: 0.35, qty: 40,
    description: 'Tender coconut water 350ml - natural electrolytes, no concentrate, single-serve tetra pack.',
    meta_description: 'Coconut water 350ml - natural electrolytes.'
  },
  {
    sku: 'GROC-B08', name: 'Green Tea Bags 25 pcs', category: 'beverages', price: 199, weight: 0.05, qty: 25,
    description: 'Green tea 25 bags - light, antioxidant-rich, individually sealed for freshness.',
    meta_description: 'Green tea 25 bags - light, antioxidant.'
  },
  // ---- Snacks & Household (9) ----
  {
    sku: 'GROC-H01', name: 'Salted Potato Chips 52g', category: 'snacks', price: 20, weight: 0.052, qty: 100,
    description: 'Classic salted potato chips 52g - thin-cut, crispy, lightly salted for tea breaks.',
    meta_description: 'Salted potato chips 52g - thin-cut, crispy.'
  },
  {
    sku: 'GROC-H02', name: 'Potato Chips 120g', category: 'snacks', price: 45, weight: 0.12, qty: 60,
    description: 'Family-size potato chips 120g - same classic salted crunch, bigger pack for sharing.',
    meta_description: 'Potato chips 120g family pack - classic salted.'
  },
  {
    sku: 'GROC-H03', name: 'Roasted Peanuts 200g', category: 'snacks', price: 89, weight: 0.2, qty: 40,
    description: 'Roasted peanuts 200g - salted, crunchy, high-protein evening snack.',
    meta_description: 'Roasted peanuts 200g - salted, high-protein.'
  },
  {
    sku: 'GROC-H04', name: 'Digestive Biscuits 250g', category: 'snacks', price: 49, weight: 0.25, qty: 50, featured: true,
    description: 'Digestive biscuits 250g - wheaty, semi-sweet, fibre-rich for chai dips.',
    meta_description: 'Digestive biscuits 250g - wheaty, chai-ready.'
  },
  {
    sku: 'GROC-H05', name: 'Instant Noodles 70g x4', category: 'snacks', price: 89, weight: 0.28, qty: 40,
    description: 'Instant noodles 70g four-pack - masala flavour, cooks in 2 minutes for hostel and home.',
    meta_description: 'Instant noodles 70g x4 masala - 2-min cook.'
  },
  {
    sku: 'GROC-H06', name: 'Dish Soap 500ml', category: 'snacks', price: 89, weight: 0.5, qty: 30,
    description: 'Lime dish soap 500ml - cuts grease in one wash, gentle on hands, refill-friendly bottle.',
    meta_description: 'Dish soap 500ml lime - grease-cut, refill bottle.'
  },
  {
    sku: 'GROC-H07', name: 'Laundry Detergent 1kg', category: 'snacks', price: 189, weight: 1.0, qty: 0, stock_availability: false,
    description: 'Powder detergent 1kg - tough on stains, gentle on fabrics. Out of stock - next supply Friday.',
    meta_description: 'Laundry detergent 1kg - stain-tough. Out of stock.'
  },
  {
    sku: 'GROC-H08', name: 'Garbage Bags 30 pcs', category: 'snacks', price: 79, weight: 0.3, qty: 40,
    description: 'Medium garbage bags 30 pcs - 19x21 inch, tear-resistant with easy-tie handles.',
    meta_description: 'Garbage bags 30 pcs medium - tear-resistant.'
  },
  {
    sku: 'GROC-H09', name: 'Kitchen Tissue Roll 2 pcs', category: 'snacks', price: 99, weight: 0.2, qty: 40,
    description: 'Kitchen tissue 2 rolls - 60 pulls each, highly absorbent for spills and oil blotting.',
    meta_description: 'Kitchen tissue 2 rolls - 60 pulls, absorbent.'
  }
];

const FEATURED_SKUS = PRODUCTS.filter((p) => p.featured).map((p) => p.sku);
const IMAGE_EXT = '.jpg';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function editorBlocks(paragraphs) {
  const time = Date.now();
  return [
    {
      id: `r__${Math.random().toString(36).slice(2, 9)}`,
      size: 1,
      className: 'md:grid-cols-1',
      columns: [
        {
          size: 1,
          id: `c__${Math.random().toString(36).slice(2, 9)}`,
          data: {
            time,
            version: '2.31.0',
            blocks: paragraphs.map((text, i) => ({
              id: `b__${i}_${Math.random().toString(36).slice(2, 8)}`,
              type: 'paragraph',
              data: { text }
            }))
          }
        }
      ]
    }
  ];
}

function slug(name) {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}

function productImages(sku) {
  const images = [];
  for (const suffix of ['-1', '-2']) {
    const rel = `grocery/${sku}${suffix}${IMAGE_EXT}`;
    if (fs.existsSync(path.join(storeRoot, 'media', rel))) {
      images.push(`/assets/${rel}`);
    }
  }
  return images.length ? images : die(`No local image found for ${sku} in store/media/grocery/`);
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
const pool = new Pool({
  host: process.env.DB_HOST,
  port: process.env.DB_PORT,
  user: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
  database: process.env.DB_NAME,
  max: 5
});

async function one(sql, params = []) {
  const { rows } = await pool.query(sql, params);
  return rows[0];
}

async function main() {
  const { default: createCategory } = await import(dist('modules/catalog/services/category/createCategory.js'));
  const { default: createProduct } = await import(dist('modules/catalog/services/product/createProduct.js'));
  const { default: createCollection } = await import(dist('modules/catalog/services/collection/createCollection.js'));
  const { createPackage } = await import(dist('modules/checkout/services/package/packageManager.js'));

  // --- 1. Wipe demo catalog data ---
  log('Deleting existing demo data...');
  await pool.query('DELETE FROM cart_item');
  await pool.query('DELETE FROM cart');
  await pool.query('DELETE FROM product');
  await pool.query('DELETE FROM category');
  await pool.query('DELETE FROM collection');
  await pool.query('DELETE FROM variant_group');
  await pool.query("DELETE FROM widget_placement WHERE widget_instance_id IN (SELECT widget_instance_id FROM widget_instance WHERE name IN ('Demo Main Menu', 'Demo Homepage Products'))");
  await pool.query("DELETE FROM widget_instance WHERE name IN ('Demo Main Menu', 'Demo Homepage Products')");
  await pool.query("DELETE FROM url_rewrite WHERE entity_type IN ('category', 'product')");

  const group = await one("SELECT attribute_group_id FROM attribute_group WHERE group_name = 'Demo Products'");
  if (!group) die("Attribute group 'Demo Products' missing - run the store seed once first");

  // --- 3. Package ---
  let pkg = await one("SELECT package_id FROM package WHERE name = 'Demo Sample Package'");
  if (!pkg) {
    log("Creating package 'Demo Sample Package'...");
    pkg = await createPackage({ name: 'Demo Sample Package', length: 30, width: 25, height: 10, weight: 0, is_default: false });
  }

  // --- 4. Categories ---
  log('Creating categories...');
  const categoryIds = {};
  for (const c of CATEGORIES) {
    const category = await createCategory({
      name: c.name,
      url_key: c.url_key,
      status: 1,
      description: editorBlocks(c.copy),
      meta_title: c.meta_title,
      meta_description: c.meta_description,
      meta_keywords: c.meta_keywords
    }, {});
    categoryIds[c.url_key] = category.category_id;
    log(`  category ${c.name} (id ${category.category_id})`);
  }

  // --- 5. Collection ---
  log("Creating collection 'homepage'...");
  const collection = await createCollection({
    name: 'Featured Products',
    code: 'homepage',
    description: editorBlocks(['Featured grocery products displayed on the homepage'])
  }, {});

  // --- 6. Products ---
  log('Creating products...');
  const productIds = {};
  for (const p of PRODUCTS) {
    const data = {
      type: 'simple',
      visibility: true,
      status: true,
      sku: p.sku,
      name: p.name,
      url_key: slug(p.name),
      price: p.price,
      weight: p.weight,
      qty: p.qty,
      manage_stock: true,
      stock_availability: p.stock_availability !== undefined ? p.stock_availability : true,
      group_id: group.attribute_group_id,
      package_id: pkg.package_id,
      category_id: categoryIds[p.category],
      meta_title: p.name,
      meta_description: p.meta_description,
      meta_keywords: `${p.category}, grocery, ${p.name}`,
      description: editorBlocks([p.description, 'Part of our hackathon demo grocery collection - fresh essentials at kirana prices, shipped across India.']),
      images: productImages(p.sku)
    };
    const product = await createProduct(data, {});
    productIds[p.sku] = product.insertId;
    log(`  product ${p.sku} ${p.name} - Rs.${p.price} (${data.images.length} image(s))${p.stock_availability === false ? ' [OOS]' : ''}`);
  }

  // --- 7. Featured grid ---
  log(`Linking ${FEATURED_SKUS.length} featured products to 'homepage' collection...`);
  for (const sku of FEATURED_SKUS) {
    await pool.query('INSERT INTO product_collection (collection_id, product_id) VALUES ($1, $2)', [collection.collection_id, productIds[sku]]);
  }

  // --- 8. Widgets ---
  log('Creating widgets...');
  const menuSettings = { menus: [], isMain: true };
  for (const c of CATEGORIES) {
    const id = crypto.randomUUID();
    menuSettings.menus.push({ id, uuid: id, name: c.name, url: `/${c.url_key}`, type: 'custom', children: [] });
  }
  const blogId = crypto.randomUUID();
  menuSettings.menus.push({ id: blogId, uuid: blogId, name: 'Blog', url: '/blog', type: 'custom', children: [] });

  const menuWidget = await one("INSERT INTO widget_instance (name, type, settings, status) VALUES ('Demo Main Menu', 'basic_menu', $1, true) RETURNING widget_instance_id", [JSON.stringify(menuSettings)]);
  await pool.query('INSERT INTO widget_placement (widget_instance_id, route, area, sort_order) VALUES ($1, $2, $3, $4)', [menuWidget.widget_instance_id, 'all', 'headerMiddleLeft', 1]);

  const homeSettings = { collection: 'homepage', count: 8, countPerRow: 4, heading: null, subText: null, viewAllLink: null, viewAllLabel: null };
  const homeWidget = await one("INSERT INTO widget_instance (name, type, settings, status) VALUES ('Demo Homepage Products', 'collection_products', $1, true) RETURNING widget_instance_id", [JSON.stringify(homeSettings)]);
  await pool.query('INSERT INTO widget_placement (widget_instance_id, route, area, sort_order) VALUES ($1, $2, $3, $4)', [homeWidget.widget_instance_id, 'homepage', 'content', 10]);

  // --- Done ---
  const { rows: counts } = await pool.query(`
    SELECT
      (SELECT count(*) FROM product) AS products,
      (SELECT count(*) FROM category) AS categories,
      (SELECT count(*) FROM collection) AS collections,
      (SELECT count(*) FROM product_image) AS images,
      (SELECT count(*) FROM product_collection) AS featured,
      (SELECT min(price) FROM product) AS min_price,
      (SELECT max(price) FROM product) AS max_price`);
  log('Summary: ' + JSON.stringify(counts[0]));
  log('Done. Start the store so event subscribers rebuild url rewrites: make store');
  await pool.end();
}

main().catch(async (e) => { die(e.stack || e.message); await pool.end().catch(() => {}); });
