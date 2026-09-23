// Verifies the new sponsored slot on xhagents.xyz in a real browser:
//   1. no ads       -> the "Advertise here" fallback shows
//   2. hostile ad   -> copy is rendered as TEXT, javascript: URLs never become links
//   3. real ad      -> card renders with a safe target/rel and its image
// ads.json is restored to its original content at the end.
import { chromium } from '/home/ubuntu/ataraxia/ataraxia-react/server/node_modules/playwright-core/index.mjs';
import fs from 'node:fs';

const EXEC = '/home/ubuntu/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome';
const ADS = '/home/ubuntu/prpo_ai/adengine/ads.json';
const SITE = 'https://xhagents.xyz/';
const ORIGINAL = fs.readFileSync(ADS, 'utf8');

let fails = 0;
const check = (n, c, d = '') => { console.log(`${c ? 'PASS' : 'FAIL'}  ${n}${d ? `  (${d})` : ''}`); if (!c) fails++; };

const browser = await chromium.launch({ executablePath: EXEC, args: ['--no-sandbox'] });
const ctx = await browser.newContext({ viewport: { width: 1280, height: 1000 } });
const page = await ctx.newPage();
let alerted = false;
page.on('dialog', async (d) => { alerted = true; await d.dismiss(); });

async function load() {
  await page.goto(SITE + '?cachebust=' + Date.now(), { waitUntil: 'networkidle', timeout: 60_000 });
  await page.waitForTimeout(1500);
}

try {
  // 1. empty
  fs.writeFileSync(ADS, '[]');
  await load();
  const sec = await page.locator('#sponsored').count();
  check('sponsored section exists on the landing page', sec === 1);
  check('empty inventory shows the advertiser CTA', /Advertise here/.test(await page.innerText('#sponsored')));
  check('no ad card when inventory is empty', (await page.locator('#sponsored .ad-card').count()) === 0);

  // 2. hostile payload written straight into ads.json (worst case: file edited by hand)
  fs.writeFileSync(ADS, JSON.stringify([{
    order_id: 'XHTEST', size: '300x250',
    title: '<img src=x onerror=alert(1)>evil',
    text: '<script>window.__pwned=1</script>click me',
    image_url: 'javascript:alert(2)',
    landing_url: 'javascript:alert(3)',
    expire: Math.floor(Date.now() / 1000) + 86400,
  }]));
  await load();
  const hostile = await page.innerText('#sponsored');
  check('hostile ad with a javascript: landing url is not rendered as an ad', (await page.locator('#sponsored .ad-card').count()) === 0);
  check('page falls back instead', /Advertise here/.test(hostile));
  check('no alert/dialog fired', alerted === false);
  check('no script injected into the page', (await page.evaluate(() => typeof window.__pwned)) === 'undefined');

  // 2b. hostile copy but a valid https link -> must render as inert text
  fs.writeFileSync(ADS, JSON.stringify([{
    order_id: 'XHTEST2', size: '300x250',
    title: '<b>Buy</b> now',
    text: 'plain text only',
    image_url: '',
    landing_url: 'https://example.com/offer',
    expire: Math.floor(Date.now() / 1000) + 86400,
  }]));
  await load();
  const card = page.locator('#sponsored .ad-card').first();
  check('a valid ad renders a card', (await card.count()) === 1);
  const link = card.locator('a').first();
  check('link points at the advertiser site', (await link.getAttribute('href')) === 'https://example.com/offer');
  check('link opens safely (noopener)', ((await link.getAttribute('rel')) || '').includes('noopener'), await link.getAttribute('rel'));
  check('link is marked sponsored/nofollow', ((await link.getAttribute('rel')) || '').includes('sponsored'));
  check('ad copy is stripped of html tags, shown as text', (await card.innerText()).includes('Buy now') && !(await card.innerHTML()).includes('&lt;b&gt;Buy'));

  // 3. with an image
  fs.writeFileSync(ADS, JSON.stringify([{
    order_id: 'XHTEST3', size: '728x90', title: 'Quiet Room',
    text: 'Breathe on Base', image_url: 'https://xhagents.xyz/favicon-xh.png',
    landing_url: 'https://ataraxia.xhagents.xyz', expire: Math.floor(Date.now() / 1000) + 86400,
  }]));
  await load();
  const img = page.locator('#sponsored .ad-card img').first();
  check('image renders when the ad has one', (await img.count()) === 1, await img.getAttribute('src'));
  check('image is capped to the bought slot width', ((await img.getAttribute('style')) || '').includes('728px'), await img.getAttribute('style'));

  // 4. expired ad must not show
  fs.writeFileSync(ADS, JSON.stringify([{
    order_id: 'XHOLD', size: '300x250', title: 'Expired', text: '', image_url: '',
    landing_url: 'https://old.example', expire: Math.floor(Date.now() / 1000) - 60,
  }]));
  await load();
  check('expired placement is hidden on the site', (await page.locator('#sponsored .ad-card').count()) === 0);
} finally {
  fs.writeFileSync(ADS, ORIGINAL);
  console.log('\nads.json restored:', fs.readFileSync(ADS, 'utf8').trim().slice(0, 40));
  await browser.close();
}

console.log(fails === 0 ? 'ALL AD-SLOT CHECKS PASSED' : `${fails} AD-SLOT CHECK(S) FAILED`);
process.exit(fails === 0 ? 0 : 1);
