// End-to-end driver. External HTTPS is relayed through Node fetch because the
// sandbox's TLS-intercepting egress isn't trusted by Chromium (Node trusts it
// via NODE_EXTRA_CA_CERTS; run with NODE_USE_ENV_PROXY=1).
// PW_EXPERIMENTAL_SERVICE_WORKER_NETWORK_EVENTS=1 makes SW fetches routable.
import { chromium } from '@playwright/test';

const BASE = process.argv[2] ?? 'http://localhost:4173';
const SHOTS = process.argv[3] ?? '/tmp/tm-shots';
const errors = [];
let simulateOffline = false;

const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_PATH || undefined,
  args: ['--disable-quic'],
});
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });

await context.route(/^https:\/\//, async (route) => {
  if (simulateOffline) return route.abort('internetdisconnected');
  const req = route.request();
  try {
    const resp = await fetch(req.url(), {
      method: req.method(),
      headers: { ...req.headers(), host: undefined },
      body: req.postDataBuffer() ?? undefined,
    });
    const body = Buffer.from(await resp.arrayBuffer());
    const headers = {};
    resp.headers.forEach((v, k) => {
      if (!['content-encoding', 'transfer-encoding', 'content-length'].includes(k.toLowerCase())) headers[k] = v;
    });
    await route.fulfill({ status: resp.status, headers, body });
  } catch (err) {
    await route.abort('failed');
  }
});

const page = await context.newPage();
page.on('console', (msg) => {
  if (msg.type() === 'error') errors.push(`console: ${msg.text()}`);
});
page.on('pageerror', (err) => errors.push(`pageerror: ${err.message}`));

const step = async (name, fn) => {
  try {
    await fn();
    await page.screenshot({ path: `${SHOTS}/${name}.png` });
    console.log(`OK   ${name}`);
  } catch (err) {
    await page.screenshot({ path: `${SHOTS}/${name}-FAIL.png` }).catch(() => {});
    console.log(`FAIL ${name}: ${err.message.split('\n')[0]}`);
    throw err;
  }
};

await step('01-load', async () => {
  await page.goto(BASE, { waitUntil: 'load' });
  await page.waitForSelector('#map canvas', { timeout: 30000 });
  await page.waitForTimeout(8000); // let tiles render + SW install
});

await step('02-add-territory-paint', async () => {
  await page.click('text=+ Add territory');
  const box = await page.locator('#map').boundingBox();
  const cx = box.x + box.width / 2;
  const cy = box.y + box.height / 2;
  for (const [dx, dy] of [[0, 0], [40, 10], [-45, 20], [15, -40], [-20, -25], [60, -15]]) {
    await page.mouse.click(cx + dx, cy + dy);
    await page.waitForTimeout(150);
  }
});

await step('03-second-territory', async () => {
  await page.click('text=+ Add territory');
  const box = await page.locator('#map').boundingBox();
  const cx = box.x + box.width / 2;
  const cy = box.y + box.height / 2;
  for (const [dx, dy] of [[140, 40], [180, 10], [150, -30], [200, 50]]) {
    await page.mouse.click(cx + dx, cy + dy);
    await page.waitForTimeout(150);
  }
});

await step('04-import-csv', async () => {
  await page.click('[data-tab="data"]');
  await page.click('text=+ Import spreadsheet');
  const csv = [
    'Name,Region,Sales,Latitude,Longitude',
    'Denver HQ,West,120000,39.7392,-104.9903',
    'Boulder Office,West,80000,40.01499,-105.27055',
    'Colorado Springs,West,64000,38.8339,-104.8214',
    'Kansas City,Central,95000,39.0997,-94.5786',
    'St Louis,Central,88000,38.627,-90.1994',
    'Wichita,Central,45000,37.6872,-97.3301',
  ].join('\n');
  await page.fill('#csv-text', csv);
  await page.click('#csv-next');
  await page.waitForSelector('#m-go');
  await page.click('#m-go');
  await page.waitForSelector('.layer-item', { timeout: 20000 });
  await page.waitForTimeout(1500);
});

await step('05-color-by-region', async () => {
  const select = page.locator('.layer-item select').first();
  await select.selectOption({ label: 'Region' });
  const sumSel = page.locator('.layer-item select').nth(1);
  await sumSel.selectOption({ label: 'Sales' });
  await page.waitForTimeout(800);
});

await step('06-geocode-one-address', async () => {
  await page.click('text=+ Import spreadsheet');
  const csv = ['Name,Address,City,State,Zip', 'White House,1600 Pennsylvania Ave NW,Washington,DC,20500'].join('\n');
  await page.fill('#csv-text', csv);
  await page.click('#csv-next');
  await page.waitForSelector('#m-go');
  await page.click('#m-go');
  await page.waitForFunction(() => document.querySelectorAll('.layer-item').length >= 2, null, { timeout: 45000 });
  await page.waitForTimeout(1000);
});

await step('07-export-png', async () => {
  const dl = page.waitForEvent('download', { timeout: 30000 });
  await page.click('#btn-export');
  await page.waitForSelector('#exp-png');
  await page.click('#exp-png');
  const download = await dl;
  await download.saveAs(`${SHOTS}/export.png`);
  await page.waitForTimeout(500);
});

await step('08-export-assignments-csv', async () => {
  await page.click('[data-tab="territories"]');
  const dl = page.waitForEvent('download', { timeout: 15000 });
  await page.click('text=Export CSV');
  const download = await dl;
  await download.saveAs(`${SHOTS}/assignments.csv`);
});

await step('09-offline-area-download', async () => {
  await page.click('[data-tab="offline"]');
  await page.waitForSelector('#area-detail');
  await page.selectOption('#area-detail', '10');
  await page.click('text=Download current view');
  await page.waitForFunction(
    () => {
      const t = document.querySelector('#toast');
      return t && !t.hidden && /Saved|failed|cancelled/.test(t.textContent || '');
    },
    null,
    { timeout: 240000 },
  );
  const toast = await page.locator('#toast').textContent();
  if (!/Saved/.test(toast)) throw new Error(`area download did not save: ${toast}`);
  await page.waitForTimeout(500);
});

await step('10-reload-offline', async () => {
  simulateOffline = true;
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#map canvas', { timeout: 30000 });
  await page.waitForTimeout(6000);
  const terrCount = await page.locator('.terr-item').count();
  if (terrCount < 2) throw new Error(`expected 2 territories after offline reload, got ${terrCount}`);
});

await step('11-online-again', async () => {
  simulateOffline = false;
  await page.waitForTimeout(1000);
});

console.log('\n--- console/page errors captured:', errors.length);
for (const e of errors.slice(0, 30)) console.log('  ' + e.slice(0, 250));
await browser.close();
process.exit(errors.some((e) => e.startsWith('pageerror')) ? 2 : 0);
