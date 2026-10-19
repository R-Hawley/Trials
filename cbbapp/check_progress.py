#!/usr/bin/env python3
"""Progress and error rate for a scrape that is still running.

Safe to run while scrape_full.py is going -- it never writes.

    py check_progress.py                # reads ncaab_raw.db
    py check_progress.py other.db
"""

import collections
import re
import sys
import traceback

try:
    from dbopen import count, open_readonly, season_of, tables
except ImportError:
    sys.exit("dbopen.py must sit in the same folder as this script.")

DB = sys.argv[1] if len(sys.argv) > 1 else "ncaab_raw.db"


def main():
    conn = open_readonly(DB)
    have = tables(conn)
    print(f"cache: {DB}\n")

    if "raw_scoreboard" not in have:
        print("  This file has no scrape tables in it.")
        print(f"  Tables found: {sorted(have) or 'none'}")
        return

    for label, table in (("scoreboard days", "raw_scoreboard"),
                         ("boxscores", "raw_boxscore"),
                         ("linescores", "raw_gameinfo"),
                         ("errors", "fetch_errors")):
        n = count(conn, table)
        print(f"  {label:18}{'  n/a' if n is None else f'{n:>7}'}")

    days = []
    if "raw_boxscore" in have:
        days = list(conn.execute(
            "SELECT day, COUNT(*) FROM raw_boxscore GROUP BY day"))

    got = collections.Counter()
    for day, n in days:
        got[season_of(day) or "unknown"] += n
    if got:
        print("\nboxscores by season")
        for season in sorted(got):
            print(f"  {season}   {got[season]:>7}")
        valid = [d for d, _ in days if season_of(d)]
        if valid:
            print(f"\nlatest day fetched: {max(valid)}")

    errs = []
    if "fetch_errors" in have:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(fetch_errors)")}
        sql = ("SELECT day, error, kind FROM fetch_errors" if "kind" in cols
               else "SELECT day, error, 'boxscore' FROM fetch_errors")
        errs = list(conn.execute(sql))

    if not errs:
        print("\nno errors logged")
        return

    kinds = collections.Counter()
    by_season = collections.Counter()
    for day, error, kind in errs:
        code = re.search(r"\b([45]\d\d)\b", error or "")
        kinds[f"{kind or '?'} {code.group(1) if code else 'other'}"] += 1
        by_season[season_of(day) or "unknown"] += 1

    print("\nerrors by type")
    for key, n in kinds.most_common():
        print(f"  {key:20} {n:>6}")

    print("\nerrors by season")
    for season in sorted(by_season):
        bad = by_season[season]
        attempts = got[season] + bad
        pct = 100 * bad / attempts if attempts else 100.0
        print(f"  {season}   {bad:>5}  ({pct:.1f}% of attempts)")

    print("\nFailures are NOT cached as successes -- re-running the same date")
    print("range later retries every one of them.")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        print("\n--- check_progress hit an unexpected error ---")
        traceback.print_exc()
        print("\nSend the lines above and I can fix it.")
        sys.exit(1)
