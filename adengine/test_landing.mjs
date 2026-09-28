// Landing page smoke test after the copy/nav/ad-slot work.
import { chromium } from '/home/ubuntu/ataraxia/ataraxia-react/server/node_modules/playwright-core/index.mjs';
const EXEC = '/home/ubuntu/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome';
let fails = 0;
const check = (n, c, d = '') => { console.log(`${c ? 'PASS' : 'FAIL'}  ${n}${d ? `  (${d})` : ''}`); if (!c) fails++; };

const browser = await chromium.launch({ executablePath: EXEC, args: ['--no-sandbox'] });
const page = await (await browser.newContext({ viewport: { width: 1280, height: 950 } })).newPage();
const errs = [];
page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text().slice(0, 140)); });
page.on('pageerror', (e) => errs.push('pageerror: ' + String(e).slice(0, 140)));

await page.goto('https://xhagents.xyz/?cb=' + Date.now(), { waitUntil: 'networkidle', timeout: 60_000 });
await page.waitForTimeout(1200);

const nav = (await page.$$eval('nav a', (as) => as.map((a) => a.innerText.trim()).filter(Boolean))).slice(0, 4); // footer nav follows
check('nav uses plain labels', JSON.stringify(nav) === JSON.stringify(['Capabilities', 'Live status', 'Products', 'Partner']), nav.join(' | '));
check('nav anchors all exist',
  (await page.locator('#features').count()) === 1 && (await page.locator('#status').count()) === 1 &&
  (await page.locator('#exhibition').count()) === 1 && (await page.locator('#community').count()) === 1);

const hero = await page.innerText('.hero');
check('hero tells a visitor what they can do', /Try it:/.test(hero) && /Trading Assistant/.test(hero) && /Advertise here/.test(hero));

const prods = await page.innerText('#exhibition');
check('every product says what it is', /quiet room on Base/.test(prods) && /affiliate showcase/.test(prods) && /pay-per-message/.test(prods));
check('products show price and status', /0\.10 USDC/.test(prods) && /Live\./.test(prods));
check('no leftover one-word product labels', !/TradingAssistant — AI Trading/.test(prods));

const community = await page.innerText('#community');
check('advertise card states the rates', /\$40\/mo/.test(community) && /\$35\/mo/.test(community) && /\$60\/mo/.test(community));
check('advertise card explains the review step', /checked before it goes live/.test(community));

const sponsored = await page.innerText('#sponsored');
check('sponsored section present', /Ad slots on XH Agents/.test(sponsored));
check('empty inventory invites advertisers', /Advertise here/.test(sponsored));

// rates modal still opens (the old "View Ad Rates" doubt)
await page.click('button[data-open-rates]');
await page.waitForTimeout(600);
const modalVisible = await page.locator('#rates-modal').isVisible().catch(() => false);
const modalText = await page.innerText('#rates-modal').catch(() => '');
check('rates modal opens and lists the same prices', modalVisible && /728/.test(modalText) && /40/.test(modalText), modalText.replace(/\n/g, ' ').slice(0, 90));
await page.locator('#rates-modal [data-close]').first().click().catch(() => page.keyboard.press('Escape'));  // the site closes these by button, not Escape
await page.waitForTimeout(300);

// product links resolve
const links = await page.$$eval('#exhibition a[href]', (as) => as.map((a) => a.getAttribute('href')));
check('product links are absolute and complete', links.every((h) => h.startsWith('https://') || h.startsWith('/')), links.join(' '));

const catalogBtn = await page.locator('button[data-open-catalog]').count();
check('catalog button (x402 endpoints) still present', catalogBtn === 1);

// ── endpoint catalogue (compact buttons + per-category pop-ups, no prices on the page) ──
const status = await page.innerText('#status');
check('catalogue section describes the endpoints', /x402 endpoints/i.test(status) && /registered on x402scan/i.test(status));
const catButtons = await page.locator('#status [data-open-ep]').count();
check('four category buttons open a list', catButtons === 4, String(catButtons));
const priceOnPage = await page.$$eval('#status .ep-wrap', (els) => els.map((e) => e.innerText).join(' '));
check('no endpoint prices exposed on the page', !/\$\s?\d+\.\d\d/.test(priceOnPage), (priceOnPage.match(/\$\s?\d+\.\d\d/) || [''])[0]);
await page.click('#status [data-open-ep="data"]');
await page.waitForTimeout(400);
const catModalOpen = await page.locator('#ep-modal-data').isVisible().catch(() => false);
const catModalText = await page.innerText('#ep-modal-data').catch(() => '');
const modalLinks = await page.locator('#ep-modal-data a[href^="/endpoints.html#"]').count();
check('a category opens a pop-up listing its endpoints as links', catModalOpen && modalLinks >= 9, `${modalLinks} links`);
check('pop-up does not expose prices', !/\$\s?\d+\.\d\d/.test(catModalText));
await page.keyboard.press('Escape');

const ep = await page.goto('https://xhagents.xyz/endpoints.html?cb=' + Date.now(), { waitUntil: 'load', timeout: 60_000 });
const epBody = await page.locator('body').textContent().catch(() => '');
const anchors = await page.locator('article.ep-card[id]').count();
check('standalone catalogue page is live and lists every endpoint', ep.status() === 200 && anchors === 17, `status ${ep.status()}, ${anchors} entries (15 registered + 2 secondary)`);
check('standalone page states how an agent pays', /How an agent pays/.test(epBody) && /X-PAYMENT/.test(epBody));

check('no console errors on the landing page', errs.length === 0, errs[0] || 'clean');
await browser.close();
console.log(fails === 0 ? '\nLANDING PAGE OK' : `\n${fails} CHECK(S) FAILED`);
process.exit(fails === 0 ? 0 : 1);
