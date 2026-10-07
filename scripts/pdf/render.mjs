#!/usr/bin/env node
/**
 * Paginate the prepared /_pdf/index.html into a PDF with headless Chrome.
 *
 * Two engines:
 *
 *   paged   (default) Injects Paged.js, which implements the parts of CSS
 *           Paged Media that Chrome does not: running heads driven by
 *           string-set, page numbers in @page margin boxes, and — the reason
 *           it is the default — target-counter(), which is what puts real
 *           page numbers in the table of contents. Slower and far more
 *           memory-hungry, because it does the layout in JavaScript.
 *
 *   chrome  Chrome's own print path. Fast and cheap, keeps PDF bookmarks and
 *           a header/footer, but the TOC gets no page numbers and @page
 *           margin boxes are ignored. The fallback if Paged.js can't hold a
 *           document this size.
 *
 * The page is loaded over HTTP from a local server (see build.sh) because the
 * site's asset URLs are root-relative. All non-local requests are blocked, so
 * a CDN outage can neither stall nor alter a release build.
 *
 * Usage:
 *   node render.mjs <url> <output.pdf> [--engine paged|chrome] [--timeout 1800]
 */

import { existsSync } from 'node:fs';
import { readFile, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const HERE = path.dirname(fileURLToPath(import.meta.url));

/**
 * Locate Paged.js's browser polyfill on disk.
 *
 * It can't be resolved by specifier: pagedjs declares an `exports` map whose
 * only entries are condition keys, so `require.resolve('pagedjs/dist/...')`
 * fails with ERR_PACKAGE_PATH_NOT_EXPORTED even though the file is right
 * there. So find the package root — via the resolver where possible, by
 * walking up node_modules otherwise — and reach into it directly.
 */
function findPagedPolyfill() {
  const roots = [];

  try {
    // Resolves to lib/index.cjs (or src/index.js); the package root is one of
    // its ancestors. Covers hoisted, nested and pnpm layouts alike.
    let dir = path.dirname(require.resolve('pagedjs'));
    for (let i = 0; i < 4; i += 1) {
      roots.push(dir);
      const parent = path.dirname(dir);
      if (parent === dir) break;
      dir = parent;
    }
  } catch {
    // Not installed where this module can see it — the walk below may still
    // find it, and if not we exit with a clear message.
  }

  for (const start of [HERE, process.cwd()]) {
    let dir = start;
    while (true) {
      roots.push(path.join(dir, 'node_modules', 'pagedjs'));
      const parent = path.dirname(dir);
      if (parent === dir) break;
      dir = parent;
    }
  }

  for (const root of roots) {
    for (const name of ['paged.polyfill.js', 'paged.polyfill.min.js']) {
      const candidate = path.join(root, 'dist', name);
      if (existsSync(candidate)) return candidate;
    }
  }
  return null;
}

// Paged.js splits selector lists with a plain `selector.split(",")` in eight
// handlers (breaks, `+`, nth-of-type, running heads, target-counter…), so
// `:is(h1, h2) + p` becomes ` h2) + p`, querySelectorAll throws, and the layout
// stops. Patched here rather than in the CSS: the site's `:is()` lists would
// otherwise have to be multiplied out, ~900 selectors for the block rhythm alone.
function splitSelectorList(list) {
  const parts = [];
  let depth = 0;
  let quote = null;
  let start = 0;
  for (let i = 0; i < list.length; i += 1) {
    const ch = list[i];
    if (quote) {
      if (ch === '\\') i += 1;
      else if (ch === quote) quote = null;
    } else if (ch === '"' || ch === "'") quote = ch;
    else if (ch === '(' || ch === '[') depth += 1;
    else if (ch === ')' || ch === ']') depth -= 1;
    else if (ch === ',' && depth === 0) {
      parts.push(list.slice(start, i));
      start = i + 1;
    }
  }
  parts.push(list.slice(start));
  return parts;
}

async function patchedPolyfill(file) {
  let patched = 0;
  const source = (await readFile(file, 'utf8')).replace(
    /\b((?:this\.)?selector)\.split\(","\)/g,
    (_, expr) => { patched += 1; return `__splitSelectorList(${expr})`; },
  );
  if (patched === 0) {
    console.warn('render: found no selector.split(",") to patch in Paged.js — a selector with a comma inside :is()/:not() may stop the layout');
  }
  return `const __splitSelectorList = ${splitSelectorList.toString()};\n${source}`;
}

function parseArgs(argv) {
  const positional = [];
  const opts = { engine: 'paged', timeout: 1800 };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--engine') opts.engine = argv[++i];
    else if (arg === '--timeout') opts.timeout = Number(argv[++i]);
    else if (arg.startsWith('--')) throw new Error(`unknown option: ${arg}`);
    else positional.push(arg);
  }
  if (positional.length !== 2) {
    throw new Error('usage: render.mjs <url> <output.pdf> [--engine paged|chrome]');
  }
  if (!['paged', 'chrome'].includes(opts.engine)) {
    throw new Error(`unknown engine: ${opts.engine}`);
  }
  [opts.url, opts.out] = positional;
  return opts;
}

const opts = parseArgs(process.argv.slice(2));
const timeoutMs = opts.timeout * 1000;

let puppeteer;
try {
  puppeteer = (await import('puppeteer')).default;
} catch {
  console.error('render: puppeteer is not installed — run `npm install`.');
  process.exit(2);
}

const started = Date.now();
const elapsed = () => `${((Date.now() - started) / 1000).toFixed(1)}s`;

const browser = await puppeteer.launch({
  headless: true,
  // Ubuntu 24.04 runners restrict unprivileged user namespaces, which is what
  // Chrome's own sandbox needs. The content is our own build output.
  args: [
    '--no-sandbox',
    '--disable-dev-shm-usage',
    '--font-render-hinting=none',
    '--disable-lcd-text',
    '--js-flags=--max-old-space-size=8192',
  ],
});

try {
  const page = await browser.newPage();
  page.setDefaultTimeout(timeoutMs);
  page.setDefaultNavigationTimeout(timeoutMs);

  const allowedHost = new URL(opts.url).host;
  await page.setRequestInterception(true);
  let blocked = 0;
  page.on('request', (request) => {
    const url = request.url();
    if (url.startsWith('data:') || new URL(url).host === allowedHost) {
      request.continue();
    } else {
      blocked += 1;
      request.abort();
    }
  });

  const failures = [];
  page.on('requestfailed', (request) => {
    const url = request.url();
    if (new URL(url).host === allowedHost) failures.push(url);
  });
  // An uncaught error once Paged.js runs means the layout has stopped and
  // __pagedDone never flips, so fail now instead of at the timeout. Errors
  // before that come from the site's own scripts and stay warnings.
  let failLayout = null;
  page.on('pageerror', (err) => {
    console.warn(`render: page error — ${err.message}`);
    if (failLayout) failLayout(err);
  });

  console.log(`render: loading ${opts.url}`);
  await page.goto(opts.url, { waitUntil: 'networkidle0', timeout: timeoutMs });

  // Images must be decoded and fonts loaded before anything measures a line
  // box, or the pagination is computed against the wrong heights.
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all(
      Array.from(document.images)
        .filter((img) => !img.complete)
        .map((img) => new Promise((res) => { img.onload = img.onerror = res; })),
    );
  });

  const pageCount = await page.evaluate(
    () => document.querySelectorAll('section.pdf-page').length,
  );
  console.log(`render: ${pageCount} doc pages loaded (${elapsed()}), ${blocked} external requests blocked`);
  if (failures.length) {
    console.warn(`render: ${failures.length} local request(s) failed, e.g. ${failures[0]}`);
  }

  let pdf;
  if (opts.engine === 'paged') {
    const polyfill = findPagedPolyfill();
    if (!polyfill) {
      throw new Error("can't find pagedjs/dist/paged.polyfill.js — run `npm install`, or use --engine chrome");
    }

    // window.PagedConfig has to exist before the polyfill executes: injecting
    // the script starts the layout, and `after` is the hook that tells us it
    // finished. Same handshake pagedjs-cli uses.
    await page.evaluate(() => {
      window.__pagedDone = false;
      window.PagedConfig = { auto: true, after: () => { window.__pagedDone = true; } };
    });
    const layoutFailed = new Promise((_, reject) => {
      failLayout = (err) => reject(new Error(`Paged.js stopped on a page error: ${err.message}`));
    });
    layoutFailed.catch(() => {}); // stays pending on success; only the race below reads it
    await page.addScriptTag({ content: await patchedPolyfill(polyfill) });

    // Laying out several hundred pages in JavaScript takes minutes, so report
    // progress instead of going quiet.
    const ticker = setInterval(async () => {
      try {
        const sheets = await page.evaluate(() => document.querySelectorAll('.pagedjs_page').length);
        console.log(`render: … ${sheets} sheets laid out (${elapsed()})`);
      } catch { /* the page is busy or gone; the wait below owns the outcome */ }
    }, 15000);
    try {
      await Promise.race([
        page.waitForFunction(() => window.__pagedDone === true, {
          timeout: timeoutMs,
          polling: 1000,
        }),
        layoutFailed,
      ]);
    } finally {
      clearInterval(ticker);
    }

    const sheets = await page.evaluate(
      () => document.querySelectorAll('.pagedjs_page').length,
    );
    console.log(`render: Paged.js laid out ${sheets} sheets (${elapsed()})`);
    if (sheets === 0) {
      throw new Error('Paged.js produced no pages — check the console warnings above');
    }

    const numbered = await page.evaluate(() => {
      const first = document.querySelector('.pdf-toc-item a');
      if (!first) return null;
      return getComputedStyle(first, '::after').content;
    });
    // null: no contents at all, which is how a single-page build (--section) is laid out.
    if (numbered !== null && (!numbered || numbered === 'none' || numbered === '""')) {
      console.warn('render: the table of contents has no page numbers — target-counter() did not resolve');
    }

    // A block Paged.js could not fit on a page (one taller than a page and
    // marked break-inside: avoid) is left in overflow columns to the right of
    // the sheet. Chrome counts that spill, clipped or not, and shrinks EVERY
    // page of the PDF to fit it, by up to 1.5x. Name the culprits.
    const spills = await page.evaluate(() => {
      const sheets = [...document.querySelectorAll('.pagedjs_page')];
      const found = [];
      sheets.forEach((sheet, i) => {
        const area = sheet.querySelector('.pagedjs_page_content');
        if (!area) return;
        const edge = area.getBoundingClientRect().right - 1;
        const out = [...area.querySelectorAll('*')].filter((el) => {
          const box = el.getBoundingClientRect();
          return box.width > 0 && box.left >= edge;
        });
        for (const el of out.filter((e) => !out.includes(e.parentElement))) {
          const cls = typeof el.className === 'string' && el.className.trim()
            ? `.${el.className.trim().split(/\s+/).slice(0, 2).join('.')}` : '';
          found.push({
            sheet: i + 1,
            el: `${el.tagName.toLowerCase()}${cls}`,
            text: el.textContent.trim().replace(/\s+/g, ' ').slice(0, 50),
            path: sheet.querySelector('[data-path]')?.dataset.path ?? null,
          });
        }
      });
      return found;
    });
    if (spills.length) {
      console.warn(`render: ${spills.length} block(s) did not fit on their page and spill sideways — Chrome will shrink every page of the PDF. Let them split (see .pdf-long-code in pdf.scss):`);
      for (const s of spills.slice(0, 8)) {
        console.warn(`  sheet ${s.sheet}, ${s.path ?? '?'}: ${s.el} "${s.text}"`);
      }
    }

    pdf = await page.pdf({
      // Paged.js has already drawn the margins, headers and page boxes into
      // the DOM, so Chrome must not add margins of its own.
      preferCSSPageSize: true,
      printBackground: true,
      margin: { top: 0, right: 0, bottom: 0, left: 0 },
      displayHeaderFooter: false,
      outline: true,
      tagged: true,
      timeout: timeoutMs,
    });
  } else {
    const furniture = (content) => `
      <div style="width:100%;font:8pt Poppins,sans-serif;color:#6b7280;
                  padding:0 18mm;display:flex;justify-content:space-between;">
        ${content}
      </div>`;
    pdf = await page.pdf({
      format: 'A4',
      printBackground: true,
      margin: { top: '20mm', right: '18mm', bottom: '18mm', left: '18mm' },
      displayHeaderFooter: true,
      headerTemplate: furniture('<span></span><span class="title"></span>'),
      footerTemplate: furniture(
        '<span></span><span><span class="pageNumber"></span> / <span class="totalPages"></span></span>',
      ),
      outline: true,
      tagged: true,
      timeout: timeoutMs,
    });
    console.warn('render: engine=chrome — the table of contents has no page numbers');
  }

  await writeFile(opts.out, pdf);
  const mb = (pdf.length / 1024 / 1024).toFixed(1);
  console.log(`render: wrote ${opts.out} (${mb} MB) in ${elapsed()}`);
} finally {
  await browser.close();
}
