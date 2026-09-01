#!/usr/bin/env node
// Fashion catalog seed for the EverShop demo store (hackathon).
// Wipes demo catalog data, then inserts 4 categories + 22 INR fashion products
// with local images (store/media/fashion/*) and a `homepage` featured collection.
//
// Run from store/ so node-config + node_modules resolve:
//   cd store
//   DB_HOST=localhost DB_PORT=5432 DB_USER=postgres DB_PASSWORD=evershop DB_NAME=evershop \
//     node ../scripts/seed_fashion.js
//
// Uses the EverShop service layer (createCategory/createProduct/createCollection/
// createPackage) for inserts - it handles variants of bookkeeping (description rows,
// inventory, attribute index, image rows). Deletes are raw SQL (FKs all cascade).
import { createRequire } from 'module';
import { fileURLToPath, pathToFileURL } from 'url';
import path from 'path';
import fs from 'fs';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const storeRoot = path.resolve(scriptDir, '..', 'store');
if (!fs.existsSync(path.join(storeRoot, 'package.json'))) {
  console.error('ERROR: store/ not found next to scripts/. Run: cd store && node ../scripts/seed_fashion.js');
  process.exit(1);
}
const dist = (p) => pathToFileURL(path.join(storeRoot, 'packages/evershop/dist', p)).href;
const require = createRequire(path.join(storeRoot, 'package.json'));
const { Pool } = require('pg');

const log = (m) => console.log(`[seed_fashion] ${m}`);
const die = (m) => { console.error(`[seed_fashion] ERROR: ${m}`); process.exit(1); };

// ---------------------------------------------------------------------------
// Catalog data (INR pricing)
// ---------------------------------------------------------------------------
const CATEGORIES = [
  {
    name: 'Kids', url_key: 'kids',
    meta_title: 'Kids Clothing - Tees, Jackets & Frocks',
    meta_description: 'Comfortable, playful kids clothing - printed cotton tees, denim jackets, hooded jackets and party frocks.',
    meta_keywords: 'kids clothing, kids t-shirt, kids frock, denim jacket kids',
    copy: ['Playful, comfy and built for playgrounds - our kids range is soft cotton first, easy washes always.', 'From birthday-party frocks to everyday tees, every piece is skin-friendly and made to move.']
  },
  {
    name: 'Women', url_key: 'women',
    meta_title: 'Women\'s Fashion - Dresses, Sarees & Palazzos',
    meta_description: 'Effortless women\'s fashion - floral midi dresses, wrap dresses, palazzo pants, silk sarees and co-ord sets.',
    meta_keywords: 'women dress, midi dress, saree, palazzo pants, co-ord set',
    copy: ['Effortless silhouettes and prints that work from desk to dinner.', 'Flowy fabrics, flattering fits - womenswear designed for real Indian weather and real life.']
  },
  {
    name: 'Men', url_key: 'men',
    meta_title: 'Men\'s Clothing - Shirts, Tees & Jackets',
    meta_description: 'Sharp everyday menswear - oxford shirts, printed casual shirts, crew-neck tees, sweatshirts and jackets.',
    meta_keywords: 'men shirt, oxford shirt, crew neck tee, bomber jacket, denim jacket',
    copy: ['Sharp staples and weekend layers - cut clean, priced honestly.', 'From boardroom-ready oxfords to bomber jackets, menswear that earns its place in your rotation.']
  },
  {
    name: 'Accessories', url_key: 'accessories',
    meta_title: 'Fashion Accessories - Belts, Sunglasses, Caps & Bags',
    meta_description: 'Finish the look - genuine leather belts, printed socks, wayfarer sunglasses, caps and leather sling bags.',
    meta_keywords: 'leather belt, sunglasses, cap, sling bag, cotton socks',
    copy: ['The finishing touches - leather, steel and canvas goods that outlast trends.', 'Small buys, big difference: belts, shades, caps and bags to finish every fit.']
  }
];

// image paths are under store/media/fashion/ -> served at /assets/fashion/...
const PRODUCTS = [
  // ---- Kids ----
  {
    sku: 'FASH-K01', name: 'Kids Printed Cotton T-Shirt', category: 'kids', price: 399, weight: 0.15, qty: 40,
    size: 'M', featured: true,
    description: 'Breathable 100% combed cotton tee with a playful water-based print that survives fifty washes and counting. Tagless neck label means zero itch during playground marathons.',
    meta_description: 'Soft printed cotton t-shirt for kids - breathable, tagless and pre-shrunk.'
  },
  {
    sku: 'FASH-K02', name: 'Kids Denim Jacket', category: 'kids', price: 1199, weight: 0.4, qty: 25, size: 'M',
    description: 'A mini take on the classic trucker - mid-wash denim with soft lining, easy-snap buttons and roomy pockets for treasures. Layers over every tee and frock in this catalog.',
    meta_description: 'Mid-wash denim jacket for kids with soft lining and snap buttons.'
  },
  {
    sku: 'FASH-K03', name: 'Kids Hooded Rain Jacket', category: 'kids', price: 999, weight: 0.35, qty: 25, size: 'L',
    description: 'Water-resistant shell with a cheerful hood keeps monsoon walks dry and bright. Tapes-sealed seams and a two-way zip make school runs in the rain genuinely easy.',
    meta_description: 'Water-resistant hooded jacket for kids - sealed seams, easy zip.'
  },
  {
    sku: 'FASH-K04', name: 'Kids Party Frock', category: 'kids', price: 899, weight: 0.2, qty: 30, size: 'S',
    description: 'Twirl-approved floral frock in soft georgette with a full cotton lining. Elasticated back panel keeps it comfortable through cake, chaos and dance performances.',
    meta_description: 'Floral georgette party frock for girls - lined, twirl-approved.'
  },
  // ---- Women ----
  {
    sku: 'FASH-W01', name: 'Floral Print Midi Dress', category: 'women', price: 1499, weight: 0.3, qty: 25, size: 'M', featured: true,
    description: 'A breezy rayon midi in an all-over floral print with a cinched waist and flared hem. Side pockets, because dresses should hold phones as well as compliments.',
    meta_description: 'Floral rayon midi dress with cinched waist and side pockets.'
  },
  {
    sku: 'FASH-W02', name: 'Floral Wrap Around Dress', category: 'women', price: 1299, weight: 0.25, qty: 25, size: 'S',
    description: 'A true wrap dress in airy crepe - adjustable tie waist, flutter sleeves and a print that flatters every body. Beach holiday or brunch, it packs like a dream.',
    meta_description: 'Adjustable floral wrap dress in airy crepe with flutter sleeves.'
  },
  {
    sku: 'FASH-W03', name: 'Off-Shoulder Party Dress', category: 'women', price: 1799, weight: 0.3, qty: 20, size: 'M',
    description: 'Crisp off-shoulder midi with a smocked bodice that stays put through every dance floor. Structured hem holds its shape from first toast to last cab home.',
    meta_description: 'Off-shoulder party dress with smocked bodice and structured hem.'
  },
  {
    sku: 'FASH-W04', name: 'Blush Palazzo Pants', category: 'women', price: 899, weight: 0.3, qty: 30, size: 'L',
    description: 'Feather-light palazzos in a blush tone with a covered elastic waist and deep pockets. Drapes like silk, breathes like cotton - your kurti\'s new best friend.',
    meta_description: 'Feather-light blush palazzo pants with elastic waist and pockets.'
  },
  {
    sku: 'FASH-W05', name: 'Art Silk Saree', category: 'women', price: 2999, weight: 0.6, qty: 15, featured: true,
    description: 'Festive art silk saree with a contrast border and gold zari motifs - a wedding-season workhorse. Comes with an unstitched blouse piece in matching silk.',
    meta_description: 'Art silk saree with zari border and matching blouse piece.'
  },
  {
    sku: 'FASH-W06', name: 'Graphic Print Co-ord Set', category: 'women', price: 1799, weight: 0.4, qty: 20, size: 'M',
    description: 'Statement co-ord with a bold graphic top and matching skirt - one outfit, zero decisions. Relaxed cuts in soft viscose keep it wearable from day to night.',
    meta_description: 'Bold graphic co-ord set in soft viscose - top and matching skirt.'
  },
  // ---- Men ----
  {
    sku: 'FASH-M01', name: 'Classic Oxford Shirt', category: 'men', price: 1499, weight: 0.3, qty: 25, size: 'L', featured: true,
    description: 'The one shirt that does everything - breathable cotton oxford with a structured collar and a cut that tucks or hangs cleanly. Meetings to weekend, no ironing drama.',
    meta_description: 'Breathable cotton oxford shirt with structured collar - office to weekend.'
  },
  {
    sku: 'FASH-M02', name: 'Printed Casual Shirt', category: 'men', price: 1299, weight: 0.3, qty: 25, size: 'M',
    description: 'Soft-washed cotton shirt with an all-over micro print and a relaxed regular fit. Rolls up well, layers better - the weekend workhorse your denim deserves.',
    meta_description: 'Soft-washed printed cotton shirt with relaxed regular fit.'
  },
  {
    sku: 'FASH-M03', name: 'Crew-Neck Cotton Tee', category: 'men', price: 599, weight: 0.2, qty: 50, size: 'M', featured: true,
    description: 'Heavyweight 180 GSM cotton tee with a reinforced neckline that refuses to sag. Pre-shrunk and cut straight - the plain tee, finally done right.',
    meta_description: 'Heavyweight 180 GSM crew-neck cotton tee, pre-shrunk.'
  },
  {
    sku: 'FASH-M04', name: 'Men\'s Fleece Sweatshirt', category: 'men', price: 1199, weight: 0.45, qty: 30, size: 'L',
    description: 'Brushed-back fleece sweatshirt with ribbed cuffs and a hood that actually stays up. Warm without the bulk - airport couch to evening walk sorted.',
    meta_description: 'Brushed fleece hoodie with ribbed cuffs - warm, not bulky.'
  },
  {
    sku: 'FASH-M05', name: 'Rust Bomber Jacket', category: 'men', price: 2499, weight: 0.6, qty: 15, size: 'L', featured: true,
    description: 'Burnished-rust bomber with a matte finish, ribbed trims and two secure inner pockets. A single layer that makes every plain tee look intentional.',
    meta_description: 'Rust bomber jacket with ribbed trims and inner pockets.'
  },
  {
    sku: 'FASH-M06', name: 'Denim Trucker Jacket', category: 'men', price: 2199, weight: 0.65, qty: 20, size: 'M',
    description: 'Rigid denim trucker that breaks in beautifully - classic waistband tabs, chest flaps and a boxy modern cut. Ages better than most investments.',
    meta_description: 'Rigid denim trucker jacket with chest flaps and modern boxy cut.'
  },
  // ---- Accessories ----
  {
    sku: 'FASH-A01', name: 'Genuine Leather Belt', category: 'accessories', price: 799, weight: 0.25, qty: 30, featured: true,
    description: 'Full-grain leather belt with a brushed metal buckle - no faux shine, no cracking edges. Ages into a patina that cheap belts only pretend to have.',
    meta_description: 'Full-grain leather belt with brushed metal buckle.'
  },
  {
    sku: 'FASH-A02', name: 'Printed Cotton Socks - Set of 3', category: 'accessories', price: 299, weight: 0.15, qty: 50,
    description: 'Three pairs of combed-cotton ankle socks with cushioned soles and statement prints. Breathable weave, reinforced toes - boring socks are a choice now.',
    meta_description: 'Combed cotton ankle socks, set of 3, cushioned soles.'
  },
  {
    sku: 'FASH-A03', name: 'Classic Wayfarer Sunglasses', category: 'accessories', price: 999, weight: 0.15, qty: 25, featured: true,
    description: 'Timeless wayfarer frame with UV400 polarized lenses and spring hinges. The silhouette that has outlived every trend since the sixties.',
    meta_description: 'Polarized wayfarer sunglasses with UV400 protection.'
  },
  {
    sku: 'FASH-A04', name: 'Round Metal Sunglasses', category: 'accessories', price: 899, weight: 0.15, qty: 25,
    description: 'Featherweight round metal frames with tinted UV400 lenses and adjustable silicon nose pads. Retro attitude, modern comfort.',
    meta_description: 'Round metal sunglasses with UV400 tinted lenses.'
  },
  {
    sku: 'FASH-A05', name: 'Classic Baseball Cap', category: 'accessories', price: 499, weight: 0.12, qty: 40,
    description: 'Structured six-panel cap in washed cotton with an adjustable metal buckle strap. Pre-curved brim, breathable eyelets - the everyday hat done properly.',
    meta_description: 'Washed cotton six-panel baseball cap with adjustable strap.'
  },
  {
    sku: 'FASH-A06', name: 'Leather Sling Bag', category: 'accessories', price: 1899, weight: 0.4, qty: 20,
    description: 'Compact crossbody in vegetable-tanned leather with a flap closure and adjustable strap. Fits phone, wallet, keys and exactly zero regrets.',
    meta_description: 'Vegetable-tanned leather sling bag with adjustable strap.'
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
    const rel = `fashion/${sku}${suffix}${IMAGE_EXT}`;
    if (fs.existsSync(path.join(storeRoot, 'media', rel))) {
      images.push(`/assets/${rel}`);
    }
  }
  return images.length ? images : die(`No local image found for ${sku} in store/media/fashion/`);
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

  // --- 1. Wipe demo catalog data (order matters only for readability; FKs cascade) ---
  log('Deleting existing demo data...');
  await pool.query('DELETE FROM cart_item');
  await pool.query('DELETE FROM cart');
  await pool.query('DELETE FROM product');      // cascades: description, images, inventory,
  //                                               attribute index, collection links, stat, relation, link
  await pool.query('DELETE FROM category');     // cascades category_description
  await pool.query('DELETE FROM collection');   // cascades product_collection
  await pool.query('DELETE FROM variant_group');
  await pool.query("DELETE FROM widget_placement WHERE widget_instance_id IN (SELECT widget_instance_id FROM widget_instance WHERE name IN ('Demo Main Menu', 'Demo Homepage Products'))");
  await pool.query("DELETE FROM widget_instance WHERE name IN ('Demo Main Menu', 'Demo Homepage Products')");
  await pool.query("DELETE FROM url_rewrite WHERE entity_type IN ('category', 'product')"); // rebuilt by event subscribers on next boot
  // Kept intentionally: attribute_group 'Demo Products' + color/size attributes + options (reused below).

  // --- 2. Attribute group + size attribute (reuse demo seed machinery) ---
  const group = await one("SELECT attribute_group_id FROM attribute_group WHERE group_name = 'Demo Products'");
  if (!group) die("Attribute group 'Demo Products' missing - run the store seed once first");
  const sizeAttr = await one("SELECT attribute_id FROM attribute WHERE attribute_code = 'size'");
  if (!sizeAttr) die("Attribute 'size' missing - run the store seed once first");

  // --- 3. Package (shippable products require one) ---
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
      status: 1, // category schema wants 0/1
      description: editorBlocks(c.copy),
      meta_title: c.meta_title,
      meta_description: c.meta_description,
      meta_keywords: c.meta_keywords
    }, {});
    categoryIds[c.url_key] = category.category_id;
    log(`  category ${c.name} (id ${category.category_id})`);
  }

  // --- 5. Collection the homepage widget renders ---
  log("Creating collection 'homepage'...");
  const collection = await createCollection({
    name: 'Featured Products',
    code: 'homepage',
    description: editorBlocks(['Featured products displayed on the homepage'])
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
      stock_availability: true,
      group_id: group.attribute_group_id,
      package_id: pkg.package_id,
      category_id: categoryIds[p.category],
      meta_title: p.name,
      meta_description: p.meta_description,
      meta_keywords: `${p.category}, fashion, ${p.name}`,
      description: editorBlocks([p.description, 'Part of our hackathon demo fashion collection - realistic pricing in INR, shipped across India.']),
      images: productImages(p.sku)
    };
    if (p.size) {
      const option = await one('SELECT attribute_option_id FROM attribute_option WHERE attribute_id = $1 AND option_text = $2', [sizeAttr.attribute_id, p.size]);
      if (option) data.attributes = [{ attribute_code: 'size', value: String(option.attribute_option_id) }];
    }
    const product = await createProduct(data, {});
    productIds[p.sku] = product.insertId;
    log(`  product ${p.sku} ${p.name} - Rs.${p.price} (${data.images.length} image(s))`);
  }

  // --- 7. Featured grid: link best products to the homepage collection ---
  log(`Linking ${FEATURED_SKUS.length} featured products to 'homepage' collection...`);
  for (const sku of FEATURED_SKUS) {
    await pool.query('INSERT INTO product_collection (collection_id, product_id) VALUES ($1, $2)', [collection.collection_id, productIds[sku]]);
  }

  // --- 8. Storefront widgets: header menu + homepage featured grid ---
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
