# PLAN: "Morning ritual" quick-entry card (mobile-first daily flow)

**Rank: 2 of 5.**
The system's core loop is: each morning, revisit *yesterday* — one memorable
moment, tick habits, log sleep. On a phone, doing that today means
side-scrolling a 10-column table and hunting for the right row. A dedicated
card at the top turns the 6 a.m. ritual into five big taps with zero
scrolling. This is the highest-impact UX change for daily retention.

## Goal

A "Morning ritual" card appears above the habit grid, pre-targeted at
**yesterday**, presenting: memorable-moment input, one large tap-row per
habit, and sleep hours + score inputs. Completing it takes under 30 seconds
one-handed. The grid stays as the month overview.

## Files to touch

| File | Change |
|---|---|
| `index.html` | new card markup, `renderRitual()`, CSS; small refactor of day-record access |

## Implementation order

1. **Refactor day access to be month-key-aware.** Current helpers `month()`
   and `day(d)` implicitly use the viewed month (`cur`). Yesterday can be in
   the *previous* month (on the 1st). Add, next to the existing `day()`:

   ```js
   function monthByKey(k) { ... }   // like month() but takes 'YYYY-MM'
   function dayByDate(dt) { ... }   // Date -> record via monthByKey
   ```

   `monthByKey` must contain the same lazy-init logic as `month()` (clone
   habits from the latest earlier month). Extract that init into a shared
   `ensureMonth(k)` so the two paths can't drift.

2. **Card markup** — insert a new `<section class="card" id="ritualCard">`
   in `index.html` directly **before** the Habit grid section. Header:
   "Morning ritual", subtitle showing the target date ("Revisiting Friday,
   July 11"), and a two-button toggle `Yesterday | Today` (yesterday
   preselected).

3. **`renderRitual()`** — renders into the card for a target `Date`:
   - memorable-moment text input (writes `rec.moment`);
   - one row per habit **of the target date's month** (not the viewed
     month): colored category dot + name + a large toggle button showing
     · / ✓ / ✗ that reuses the existing `cycle()` function; number habits
     render an inline numeric input instead;
   - sleep hours (step 0.5) and sleep score inputs writing `sleepH` /
     `sleepScore`.
   All writes go through `dayByDate`, call `save()`, and — **only when the
   target date is inside the currently viewed month** — also refresh
   `renderGrid()` and `renderChart()` so the spread stays in sync.

4. **Completion feedback.** At the top of the card show "n of m done" where
   m = number of check-type habits + 1 (moment) + 1 (sleep hours), counting
   filled entries. Plain text, no animation.

5. **CSS** — habit rows: `display:flex`, min-height 48px, full-width tap
   target, hairline separators (reuse `--gridline`); the toggle button ≥ 44px
   square. Reuse existing tokens only; no new colors.

6. **Wire-up** — call `renderRitual()` from `renderAll()`, and re-render it
   after habit add/remove (`#addHabit` submit handler and the delete handler
   in `renderHabits()`).

## Edge cases a weaker model would miss

- **The 1st of the month.** Yesterday belongs to the previous month: its
  habit list may differ, and the record must be written into the previous
  month's `days` — never into day 0 or day 31 of the viewed month. Compute
  yesterday as `new Date(y, m, d - 1)` (JS rolls over correctly) and route
  everything through `dayByDate`.
- **The ritual card ignores month navigation.** It always targets
  yesterday/today *in real time*, even while the user is browsing March.
  Guard the `renderGrid()`/`renderChart()` sync with a same-month check or
  browsing history will repaint with wrong-month data.
- **Habit list source.** Rows must come from the *target date's* month
  record — after a month rollover, yesterday's habits are last month's list,
  including habits since removed.
- **Number habits** (weight) have no ✓/✗ state; they need the numeric input
  path, and blank must store `undefined`/`null`, never `NaN` or `0`.
- **Avoid-category habits**: ✓ means *slipped* (see grid legend). Keep the
  same glyphs and colors as the grid — do not "fix" the polarity in one
  place only.
- **Do not duplicate state.** The card and the grid must read/write the same
  records via the same helpers. No parallel "ritual" data structure.
- **Sleep inputs write to yesterday** (the night just slept), matching how
  the video logs it — not to today.

## Acceptance criteria

1. On July 12 with June/July data present, the card shows July 11; toggling
   a habit there flips the same cell in the grid instantly.
2. Set the system date to the 1st: the card targets the last day of the
   previous month, and entries land in that month (verify by navigating back
   a month; also verify no `days["0"]` key appears in the export JSON).
3. The Yesterday/Today toggle switches targets and re-labels the date line.
4. While viewing a past month, using the ritual card changes nothing visible
   in that month's grid, but the data is present when navigating to the
   current month.
5. A number habit accepts `83.5`; clearing it removes the value from the
   export JSON rather than storing 0.
6. At 390px viewport width every ritual row is a single un-cramped line and
   all tap targets are ≥ 44px tall.
