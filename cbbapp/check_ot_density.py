#!/usr/bin/env python3
"""Does overtime score at the same per-minute rate as regulation?

pace_40 scales possessions by 40/minutes, which assumes play is uniformly
dense across regulation and OT. The boxscore can't confirm that -- it has no
per-period shot counts -- but the linescore has per-period POINTS, which is a
usable proxy: if OT scores at close to the regulation per-minute rate, the
uniform assumption is reasonable. If it doesn't, pace_40 is biased for the
329 OT games and the play-by-play endpoint is worth the extra fetch.

    py check_ot_density.py                 # reads ncaab_raw.db
    py check_ot_density.py other.db

Writes ot_density.txt -- attach that in chat.
"""

import collections
import json
import sqlite3
import statistics
import sys

DB = sys.argv[1] if len(sys.argv) > 1 else "ncaab_raw.db"
REG_MIN = 40
OT_MIN = 5

_lines = []


def out(text=""):
    print(text)
    _lines.append(str(text))


def classify(label):
    """Same rules as the scraper: -> ("h", n) | ("ot", n) | (None, None)."""
    import re
    text = "".join(str(label).split()).upper().replace("-", "").replace("_", "")
    if text in ("1", "1ST", "1H", "H1", "1STHALF", "FIRSTHALF"):
        return ("h", 1)
    if text in ("2", "2ND", "2H", "H2", "2NDHALF", "SECONDHALF"):
        return ("h", 2)
    if text.isdigit():
        return ("ot", int(text) - 2)
    m = re.fullmatch(r"(\d+)OT", text)
    if m:
        return ("ot", int(m.group(1)))
    m = re.fullmatch(r"OT(\d*)", text)
    if m:
        return ("ot", int(m.group(1)) if m.group(1) else 1)
    return (None, None)


try:
    from dbopen import open_readonly, tables
except ImportError:
    sys.exit("dbopen.py must sit in the same folder as this script.")

conn = open_readonly(DB)
if "raw_gameinfo" not in tables(conn):
    sys.exit(f"{DB} has no raw_gameinfo table -- nothing to analyse yet.")

by_ot = collections.defaultdict(list)
reg_rates_all = []

for text, in conn.execute("SELECT payload FROM raw_gameinfo"):
    try:
        contests = json.loads(text).get("contests") or []
        contest = contests[0] if contests else {}
    except Exception:  # noqa: BLE001
        continue
    reg_pts = 0
    ot_pts = 0
    n_ot = 0
    ok = True
    for entry in (contest.get("linescores") or []):
        if not isinstance(entry, dict):
            continue
        kind, num = classify(entry.get("period", ""))
        try:
            both = int(entry.get("home") or 0) + int(entry.get("visit") or 0)
        except (TypeError, ValueError):
            ok = False
            break
        if kind == "h":
            reg_pts += both
        elif kind == "ot":
            ot_pts += both
            n_ot = max(n_ot, num)
        else:
            ok = False
            break
    if not ok or not reg_pts:
        continue
    reg_rate = reg_pts / REG_MIN
    reg_rates_all.append(reg_rate)
    if n_ot:
        by_ot[n_ot].append((reg_rate, ot_pts / (OT_MIN * n_ot)))

out(f"cache: {DB}")
out()
out(f"regulation scoring rate, all {len(reg_rates_all)} games")
out(f"  {statistics.mean(reg_rates_all):.3f} points/minute (both teams)")
out()

if not by_ot:
    out("No overtime games found.")
else:
    out("overtime vs regulation, per minute (both teams)")
    out(f"  {'':6} {'games':>6} {'reg/min':>9} {'OT/min':>9} {'ratio':>8} "
        f"{'median':>8}")
    all_ratios = []
    for n in sorted(by_ot):
        rows = by_ot[n]
        reg = statistics.mean(r for r, _ in rows)
        ot = statistics.mean(o for _, o in rows)
        ratios = [o / r for r, o in rows if r]
        all_ratios += ratios
        out(f"  {n}OT    {len(rows):>6} {reg:>9.3f} {ot:>9.3f} "
            f"{ot / reg:>8.3f} {statistics.median(ratios):>8.3f}")
    mean_ratio = statistics.mean(all_ratios)
    out(f"  {'all':6} {len(all_ratios):>6} {'':>9} {'':>9} "
        f"{mean_ratio:>8.3f} {statistics.median(all_ratios):>8.3f}")
    out()
    out(f"spread: {statistics.pstdev(all_ratios):.3f} sd, "
        f"min {min(all_ratios):.2f}, max {max(all_ratios):.2f}")
    out()
    out("reading it")
    out("  ratio ~1.00  OT plays at the regulation rate -> pace_40's uniform")
    out("               assumption is sound, no play-by-play needed")
    out("  ratio >1.00  OT is denser than regulation -> pace_40 UNDER-corrects")
    out("  ratio <1.00  OT is sparser -> pace_40 OVER-corrects")
    off = abs(mean_ratio - 1) * 100
    out()
    if off < 5:
        out(f"  -> {off:.1f}% off uniform. Within noise; pace_40 is fine as is.")
    elif off < 12:
        out(f"  -> {off:.1f}% off uniform. Real but small, and it only touches "
            f"{len(all_ratios)} of {len(reg_rates_all)} games.")
    else:
        out(f"  -> {off:.1f}% off uniform. Large enough to matter; the "
            f"play-by-play route is worth the extra fetch.")
    out()
    out("  Caveat: points are a proxy for possessions. Late-game fouling adds")
    out("  free throws, which lifts points per minute more than possessions,")
    out("  so a mild ratio above 1.0 likely overstates the pace difference.")

with open("ot_density.txt", "w", encoding="utf-8") as fh:
    fh.write("\n".join(_lines))

print()
print("=" * 60)
print(" DONE. Attach ot_density.txt in chat.")
print("=" * 60)
