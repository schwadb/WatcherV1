// Take a 1920x1080 screenshot of the dashboard with headless Chromium.
// Usage: node tools/screenshot.mjs http://127.0.0.1:8080 out.png [wait-seconds]
// Needs Playwright for Node (npm i -g playwright, or the preinstalled copy in the dev container).
import { createRequire } from "node:module";
const { chromium } = createRequire(import.meta.url)("playwright"); // honors NODE_PATH for a global install

const [url = "http://127.0.0.1:8080", out = "dashboard.png", waitSeconds = "6"] = process.argv.slice(2);
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, ignoreHTTPSErrors: true });
const logs = [];
page.on("console", (m) => { if (["error", "warning"].includes(m.type())) logs.push(`${m.type()}: ${m.text()}`); });
page.on("pageerror", (e) => logs.push(`pageerror: ${e.message}`));
await page.goto(url, { waitUntil: "load" });
await page.waitForTimeout(Number(waitSeconds) * 1000);
await page.screenshot({ path: out });
console.log("saved", out);
if (logs.length) console.log("browser console:\n  " + logs.join("\n  "));
await browser.close();
