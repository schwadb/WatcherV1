# PLAN: Streaks and monthly stats

**Rank: 3 of 5.**
The grid records; it doesn't motivate. Streak counts and completion rates
are the payoff loop of every successful habit tracker ("don't break the
chain"), and all the data already exists. This is high value at low risk —
purely additive rendering.

## Goal

Each habit shows a current streak, best streak, and month completion rate.
A compact stats strip summarizes the month. Streaks are computed across
month boundaries, in real time, with polarity-correct handling of
avoid-category habits.

## Files to touch

| File | Change |
|---|---|
| `index.html` | `computeStreaks()`, `renderStats()`, extra tfoot row, stats strip markup + CSS |

## Implementation order

1. **Define "success" per habit category** (single helper, used everywhere):
   - `non` / `build` check habits: success = `vals[id] === 'done'`.
   - `avoid` check habits: success = `vals[id] === 'miss'` (✗ = resisted;
     ✓ = slipped, per the existing grid legend).
   - `number` habits (weight): excluded from streaks entirely; their stat is
     the existing average plus month delta (last − first logged value).

2. **`computeStreaks(habitId)`** — walk backwards day-by-day from *today*
   (real date, not the viewed month) using date arithmetic
   (`new Date(y, m, d - 1)` rolls across months) and reading records via the
   month-key lookup:
   - **Current streak**: consecutive successful days ending at today or
     yesterday. Today counts if already marked successful; an *unmarked*
     today does NOT break the streak (the day isn't over) — but an unmarked
     yesterday does.
   - Stop walking after 366 iterations or when reaching a date before the
     earliest month key in `state.months` — whichever comes first.
   - **Best streak**: longest run across all stored history. Compute by
     iterating stored months in sorted key order, day by day, with the same
     success predicate.

3. **Grid integration** — add a second `tfoot` row under the existing Σ row:
   label cell "🔥", then per check-habit column `cur` (current streak,
   muted when 0), formatted as plain number. Tooltip (`title`): "current
   streak · best N".

4. **Stats strip** — small card between the grid and the sleep chart (or a
   flex row inside the grid card footer): for the *viewed* month show
   "Perfect days: X" (every non-negotiable successful), "Best habit:
   NAME (NN%)", "Needs work: NAME (NN%)". Completion % = successful days ÷
   days elapsed in that month (see edge cases). Use text tokens; no new
   colors; numbers in `tabular-nums`.

5. Recompute in `renderFooter()` (already called after every cell change) —
   streak math over ~12 months × 31 days × ~8 habits is trivially cheap; no
   caching needed.

## Edge cases a weaker model would miss

- **Avoid-habit polarity.** In this app ✓ on an avoid habit means *slipped*.
  Naively counting ✓ as success makes "Socials on waking" show a streak for
  relapsing daily. The success predicate in step 1 is the whole game.
- **Blank vs miss.** Blank cells in the past break current streaks (the day
  wasn't done), but an unmarked *today* must not — users fill the ritual in
  the morning for yesterday, so at 7 a.m. every streak would read 0.
- **Month boundaries.** Walking `days[d-1]` inside one month's record breaks
  every streak on the 1st. Use real `Date` arithmetic + month-key lookup.
- **Days elapsed, not days in month.** Completion % against 31 days on July
  12 caps everyone at 39%. For the current month divide by *today's date*;
  for past months divide by the month length; for future months show "—".
- **Habits added mid-month / absent months.** A habit id may be missing from
  earlier months' habit lists. For **best streak**, only iterate months
  where the id exists in that month's `habits`; a month where the habit
  isn't listed *pauses* rather than breaks the run is WRONG — treat it as a
  boundary (streak ends). Keep the rule simple and stated in a code comment.
- **Removed habits** exist in `days[*].vals` but not in `m.habits`; skip
  them — never resurrect columns via stats.
- **Don't crash on empty state.** New device with no marks: all streaks 0,
  strip shows placeholders, no exceptions in console.

## Acceptance criteria

1. Mark a build habit ✓ on the last 3 days of June and the first 2 of July:
   current streak shows 5 on July 2 (verify by seeding localStorage and
   freezing the date via a `?today=2026-07-02` test override or Playwright
   clock).
2. An avoid habit with ✗ marked 4 days running shows streak 4; marking
   today ✓ (slipped) drops it to 0.
3. At 7 a.m. with today untouched but yesterday successful, streaks are
   unchanged from last night (unmarked today doesn't zero them).
4. On July 12, a habit successful 6 of 12 elapsed days shows 50%, not 19%.
5. A brand-new profile renders with zero console errors and all-zero stats.
6. The added tfoot row and stats strip render correctly in dark mode and at
   390px width (numbers never overflow their columns).
