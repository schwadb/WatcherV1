# PLAN: Full habit management (rename, reorder, recategorize, restore)

**Rank: 4 of 5.**
Habits can currently only be added or removed. Fixing a typo means deleting
the habit — which orphans its history. Reordering (the video groups
non-negotiables first) is impossible. This unblocks the natural monthly
evolution the whole system is built around ("next month" list → real habit).

## Goal

From the Habits card: rename, change category, change type, move up/down,
remove, and **restore** a previously removed habit with its history intact.
All edits apply to the currently viewed month only (past months keep their
own lists — that's the existing per-month design).

## Files to touch

| File | Change |
|---|---|
| `index.html` | edit UI in `renderHabits()`, reorder buttons, restore section, CSS |

## Implementation order

1. **Inline edit mode.** In `renderHabits()`, give each `.hrow` an Edit
   button (✎). Clicking swaps the row's static name/meta for: text input
   (name), category `<select>`, type `<select>`, Save / Cancel. Save mutates
   the existing habit object **in place** — `h.name = …; h.cat = …;
   h.type = …` — never replaces its `id`. Then `save(); renderGrid();
   renderHabits();`.

2. **Reorder.** Add ▲ / ▼ buttons per row that swap the habit with its
   neighbor in `month().habits` (first row's ▲ and last row's ▼ disabled).
   Order is already respected everywhere because `renderGrid()` and
   `renderFooter()` iterate `m.habits` — no other change needed.

3. **Restore removed habits.** Below the add form, render a "Hidden this
   month" list: scan `Object.values(m.days)` for `vals` keys that are not in
   `m.habits.map(h => h.id)`, count marked days per orphan id. For each,
   show "id — N days of data · Restore". Restoring needs name/cat/type,
   which the current delete flow discards, so:

4. **Change delete to soft-hide.** Replace the filter-out delete with
   `h.hidden = true`. Every consumer that iterates habits —
   `renderGrid()` (header + rows), `renderFooter()`, `renderHabits()` main
   list — must filter `!h.hidden`. Restore = `delete h.hidden`. The
   "Hidden this month" list from step 3 then reads
   `m.habits.filter(h => h.hidden)` (keep the orphan-id scan as a fallback
   for data hidden by the *old* hard-delete, restoring with
   `cat:'build', type:'check'` defaults and the id as the name).
   Update the delete confirm text to say "hide".

5. **Type-change safety.** When type flips check→number, old `'done'/'miss'`
   strings would render as NaN in a number input; when number→check, old
   numbers aren't `'done'`/`'miss'`. Both cell renderers must tolerate
   wrong-type values by treating them as blank (do NOT delete the underlying
   data — the user may flip back).

## Edge cases a weaker model would miss

- **`id` is the join key to history.** Rename must never regenerate the id;
  if it does, every past ✓ silently detaches. This is the invariant the
  whole plan protects.
- **Per-month lists are a feature.** Edits apply to `month().habits` (the
  viewed month) only. "Fixing" past months' names retroactively falsifies
  the record; leave them alone. New months clone the latest earlier list, so
  future months inherit edits automatically via the existing
  `prevMonthWithHabits()` logic.
- **`DEFAULT_HABITS` ids collide across profiles** (`weight`, `cold`, …).
  When restoring an orphan or adding a new habit, check the id isn't already
  present in `m.habits` (including hidden ones) before inserting.
- **Weight's two-column note.** Number habits render a 58px input
  (`td.numcell`); a check habit converted to number inherits that width
  automatically — but confirm the header rotation still fits, since number
  headers are the widest.
- **The footer Σ row** counts per type. After a type change it must follow
  the *current* type while ignoring wrong-type historical values (step 5's
  tolerance rule applies there too — `filter(v => typeof v === 'number')`
  style guards, not `Boolean` guards, because a logged `0` is valid).
- **Reorder + hidden interplay.** ▲/▼ must swap positions within the
  *visible* subsequence without displacing hidden entries in ways that make
  them reappear in odd spots when restored. Simplest correct approach: swap
  actual array positions of the two visible habits involved.
- **Escape hatch for concurrent grid renders.** Edit mode lives in
  `renderHabits()`'s DOM; a grid cell tap re-renders only the grid, so open
  edit rows must survive — do not call `renderHabits()` from the cell-toggle
  path (it currently doesn't; keep it that way).

## Acceptance criteria

1. Rename "Cold exposure" → "Cold shower": all existing ✓ marks remain in
   the grid; export JSON shows the same habit id with the new name.
2. Move a habit up: grid columns reorder immediately and the order persists
   after reload; next month's auto-created list inherits the new order.
3. Hide a habit with 10 marked days, reload, restore it: column returns with
   all 10 marks.
4. Data hidden by the old hard-delete (simulate: manually remove a habit
   entry from localStorage JSON while leaving its vals) appears under
   "Hidden this month" and is restorable.
5. Flip a check habit to number and back: no NaN anywhere, no console
   errors, historical ✓ marks reappear intact after flipping back.
6. June's habit list is byte-identical in the export before and after any
   edits made while viewing July.
