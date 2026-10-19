# NCAA D1 men's basketball scraper — audit tooling

Companion scripts for `scrape_full.py`, the standalone collector that feeds the
pace/style app. Nothing here imports the app, and the app does not import any of
this — the scraper's only outputs are a spreadsheet and a SQLite cache.

Source: `https://ncaa-api.henrygd.me` (rate limit 5 req/s; the scraper throttles
below that). `--base-url` points it at a self-hosted instance.

> **`scrape_full.py` is not in this repo yet.** The working copy lives on the
> local machine at `C:\Users\Rober\Downloads\cbbapp`. It needs to be committed
> here to be version controlled alongside these scripts.

## Files

| File | What it is |
|---|---|
| `dbopen.py` | Shared read-only cache opener. **Required by all three `check_*` scripts** — never run directly. |
| `check_progress.py` | Coverage and error rates, broken down by season. Safe to run mid-scrape. |
| `check_periods.py` | Audits period labels in the cache. Writes `period_audit.txt`. |
| `check_ot_density.py` | Tests whether OT scores at the regulation per-minute rate. Writes `ot_density.txt`. |

All four go in the same folder as the cache. Run from that folder:

```
py check_progress.py                 # defaults to ncaab_raw.db
py check_progress.py other.db
```

## Why `dbopen.py` exists

The scraper runs its cache in WAL mode — that was the fix for a lock crash that
killed a five-hour run. But a URI `mode=ro` connection to a WAL database has to
touch the `-shm` sidecar, and SQLite raises rather than degrading when it can't.
A running scrape owns that sidecar, so all three audit scripts broke the moment
WAL was turned on, for a reason that had nothing to do with the data.

`open_readonly()` tries the strict read-only open first and settles for a normal
connection when that fails. Neither path ever writes. The scripts also tolerate
a cache that predates a schema change, both the old and new `fetch_errors`
layouts, and unparseable dates, and `check_progress.py` prints a real traceback
instead of dying silently.

## Why the cache matters

Every raw payload is stored before it is parsed. Two consequences, both already
paid off:

- **Re-runs are resumable.** Failures are never cached as successes, so
  re-running a date range retries exactly what failed and re-fetches nothing
  else.
- **Parser fixes are free.** The `2OT`/`3OT` label bug, and adding `season` /
  `periods` / `minutes` / `pace_40`, were each a `--skip-fetch` re-export
  measured in seconds rather than a re-scrape measured in hours.

## Periods

The boxscore endpoint carries 18 stats but no time dimension at all — its only
period field reads `FINAL`. Per-period scoring comes from `/game/{id}` under
`contests[0].linescores`, a separate fetch per game.

Label handling is deliberately strict. `1`/`1ST`/`1H`/`H1`, the same for the
second half, bare digits above 2 (`3` → OT1), `2OT`-style and `OT`/`OT2`-style
are recognised. **Anything unrecognised is excluded and logged rather than
folded into a half** — a mislabelled period silently added to `h2_pts` would be
invisible, whereas an excluded one shows up in `scrape_log` and in the
halves-plus-OT-vs-boxscore-total check that runs on every team row.

That check is what caught the `2OT` bug: those 51 games were already flagged
twice each before anyone noticed the totals were short.

## Pace

```
possessions = fga - oreb + tov + 0.475 * fta
pace_40     = pace * (40 / minutes),  minutes = 40 + 5 * num_ot
```

This assumes play is uniformly dense across regulation and overtime.
`check_ot_density.py` tests that using per-period points as a proxy. Measured
deviation moves an individual OT game's pace by a few percent and a season
average by well under a tenth of a percent, so the uniform scaling stands. Note
the caveat the script prints: late-game fouling inflates points per minute more
than it inflates possessions, so the proxy overstates the gap.

One finding worth carrying into any archetype work — OT games have *lower*
regulation scoring rates than average, monotonically by OT count (1OT 3.601,
2OT 3.587, 3OT 3.300 vs a 3.722 league mean). Grindy games are the ones that go
long.
