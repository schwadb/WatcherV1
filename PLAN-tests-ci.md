# PLAN: Playwright smoke tests + CI gate before deploy

**Rank: 5 of 5 — do before shipping plans 1–4, ideally right after plan 1.**
Every push to `main` deploys straight to the phone with zero checks. One
broken paren in the single 34 KB `index.html` bricks the live app until
someone notices. A 60-second smoke suite that gates the Pages deploy makes
all the other plans safe to execute — especially by a less capable model.

## Goal

`npm test` runs a Playwright suite covering boot, persistence, grid
interaction, chart rendering, month navigation, and export. The Pages
workflow runs it first; deploy only happens on green.

## Files to touch

| File | Change |
|---|---|
| `package.json` | **new** — `@playwright/test` devDependency, `test` script |
| `playwright.config.js` | **new** — chromium project, local static server |
| `tests/watcher.spec.js` | **new** — the smoke suite |
| `tests/seed.js` | **new** — shared seed-data builder |
| `.github/workflows/pages.yml` | add `test` job; make `deploy` depend on it |
| `.gitignore` | **new** — `node_modules/`, `test-results/`, `playwright-report/` |

## Implementation order

1. **`package.json`**: `"devDependencies": { "@playwright/test": "^1.49.0" }`,
   `"scripts": { "test": "playwright test" }`. No other deps.

2. **`playwright.config.js`**: single chromium project;
   `webServer: { command: "npx http-server -p 4173 .", url: "http://127.0.0.1:4173", reuseExistingServer: true }`
   — pages must be served over http, not file://, because localStorage
   isolation and (after PLAN-pwa-offline) service workers behave differently
   on file://. Use `python3 -m http.server 4173` instead if avoiding the
   extra npx download is preferred.

3. **`tests/seed.js`**: export `buildSeed({ monthKey, days })` producing the
   exact localStorage shape (`{ version: 1, months: { [monthKey]: {
   intention, goals, nextMonth, habits, days } } }`) with the six default
   habits. Every test seeds via
   `page.addInitScript(s => localStorage.setItem('watcher-v1', s), JSON.stringify(seed))`.

4. **`tests/watcher.spec.js`** — the suite (each test navigates to `/`):
   - **boot empty**: no seed → header shows current month/year; zero page
     errors (attach a `page.on('pageerror')` collector to every test via
     `test.beforeEach`; assert empty at the end — this catches syntax errors
     anywhere in the file).
   - **cell cycle**: tap one habit cell 3 times → ✓ then ✗ then blank;
     reload → state persisted.
   - **number habit**: type `83.5` into the weight cell, reload, still
     `83.5`; footer average updates.
   - **sleep chart**: seed 15 days of hours → exactly 15 `circle` dot pairs
     (30 circles) inside `#sleepChart`; seed zero days → "No sleep logged
     yet" text node present.
   - **tooltip**: hover mid-chart → `#chartTip` becomes visible and contains
     an `h` value.
   - **month navigation**: click `‹` then `›` → original month's data
     intact; new month inherits the habit list (header count matches).
   - **journal**: pick day 2, type an entry + one gratitude, reload → both
     present; day chip 2 gets the `has` class.
   - **export shape**: click Export, capture the download
     (`page.waitForEvent('download')`), parse JSON → `version === 1` and the
     seeded month key exists.
5. **CI wiring** in `.github/workflows/pages.yml`: new `test` job before
   `deploy`:

   ```yaml
   test:
     runs-on: ubuntu-latest
     steps:
       - uses: actions/checkout@v4
       - uses: actions/setup-node@v4
         with: { node-version: 22 }
       - run: npm ci || npm i
       - run: npx playwright install --with-deps chromium
       - run: npx playwright test
   deploy:
     needs: test
     ...
   ```

   Keep `deploy`'s existing contents; only add `needs: test`. Also add
   `pull_request:` to the `on:` block so PRs get the test job (the deploy
   job must additionally be guarded with
   `if: github.event_name != 'pull_request'`).

## Edge cases a weaker model would miss

- **There is no lockfile yet**, so bare `npm ci` fails on first CI run —
  hence `npm ci || npm i`. Better: commit `package-lock.json` (run
  `npm i` locally once) and use plain `npm ci`.
- **The upload-pages-artifact step uploads the repo root**, which after this
  plan contains `node_modules/` and `test-results/` in CI. The test job and
  deploy job are separate runners so deploy's checkout stays clean — but
  only as long as deploy never runs `npm i`. Do not "optimize" them into one
  job without adding an artifact exclude.
- **Playwright in this dev container**: browsers live at
  `/opt/pw-browsers` (`PLAYWRIGHT_BROWSERS_PATH`); never run
  `playwright install` locally here — but CI runners DO need
  `npx playwright install --with-deps chromium`. The two environments
  differ; the config must not hardcode either path.
  If a local run hits a browser-resolution error, launch with
  `executablePath: '/opt/pw-browsers/chromium'` via an env-guarded override
  rather than downloading.
- **Today-dependence.** The app highlights today and the ritual/streak
  features (plans 2–3) depend on the real date. Seed data must be built
  relative to `new Date()` (current month key), not hardcoded to
  `2026-07`, or the suite starts failing in August. Playwright's
  `page.clock` API can pin the date for date-sensitive assertions.
- **The chart is drawn after a ResizeObserver-less initial pass** — dots
  exist immediately, but assert with `await expect(...).toHaveCount(...)`
  (auto-retrying) rather than a bare count-once, to absorb render timing.
- **Download assertions need a real browser context** — `download.path()`
  is null in some headless configs unless `acceptDownloads` (default true in
  @playwright/test) is on; don't disable it.

## Acceptance criteria

1. `npm test` passes locally in this repo's dev container and finishes in
   under 90 seconds.
2. Introduce a deliberate syntax error in `index.html`'s script; `npm test`
   fails on the pageerror assertion (proves the canary works). Revert.
3. A PR touching `index.html` shows the `test` check; `main` remains
   undeployed until `test` is green (`deploy` shows `needs: test` chaining
   in the Actions graph).
4. A push to `main` with green tests still deploys to
   https://schwadb.github.io/WatcherV1/ exactly as before.
5. The published Pages site does not contain `node_modules/` (spot-check
   `https://schwadb.github.io/WatcherV1/node_modules/` → 404).
6. The suite passes in the first week of any month (no hardcoded dates).
