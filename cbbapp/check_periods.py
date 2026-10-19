#!/usr/bin/env python3
"""Audit the period labels sitting in a scraped cache.

Answers three questions in one pass:
  1. Is gameinfo coverage complete, or did the linescore pass not finish?
  2. What period labels does the feed actually use for overtime?
  3. How many 1OT / 2OT / 3OT games are in there?

    py check_periods.py                 # reads ncaab_raw.db
    py check_periods.py other.db

Writes period_audit.txt -- attach that in chat.
"""

import collections
import json
import re
import sqlite3
import sys

DB = sys.argv[1] if len(sys.argv) > 1 else "ncaab_raw.db"

_lines = []


def out(text=""):
    print(text)
    _lines.append(str(text))


def classify(label):
    """Same rules as the scraper: -> ("h", n) | ("ot", n) | (None, None)."""
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
    from dbopen import open_readonly
    from dbopen import count as _count
except ImportError:
    sys.exit("dbopen.py must sit in the same folder as this script.")

conn = open_readonly(DB)


def count(table):
    return _count(conn, table)


out(f"cache: {DB}")
out()
out("coverage")
n_box = count("raw_boxscore")
n_gi = count("raw_gameinfo")
out(f"  raw_scoreboard   {count('raw_scoreboard')} days")
out(f"  raw_boxscore     {n_box} games")
if n_gi is None:
    out("  raw_gameinfo     MISSING TABLE - this cache predates the period fetch")
    sys.exit(0)
out(f"  raw_gameinfo     {n_gi} games")
if n_box and n_gi is not None and n_gi < n_box:
    out(f"  -> {n_box - n_gi} games have a boxscore but NO linescore yet;")
    out("     the period pass has not finished. Re-run the scrape to fill them.")
out()

rows = conn.execute("SELECT day, payload FROM raw_gameinfo ORDER BY day")
labels = collections.Counter()
unknown_labels = collections.Counter()
by_ot = collections.Counter()
examples = collections.defaultdict(list)
unknown_games = []
no_linescore = []
days = []

for day, text in rows:
    days.append(day)
    try:
        contests = (json.loads(text).get("contests") or [])
        contest = contests[0] if contests else {}
    except Exception:  # noqa: BLE001
        continue
    ls = contest.get("linescores") or []
    if not ls:
        no_linescore.append(contest.get("id"))
        continue
    seen = []
    n_ot = 0
    bad = []
    for entry in ls:
        if not isinstance(entry, dict):
            continue
        lab = str(entry.get("period", "")).strip()
        labels[lab] += 1
        seen.append(lab)
        kind, num = classify(lab)
        if kind == "ot":
            n_ot = max(n_ot, num)
        elif kind is None:
            unknown_labels[lab] += 1
            bad.append(lab)
    # Count by OT periods the scraper actually RECOGNISES, not by raw period
    # count -- an unrecognised label must not inflate a game into overtime.
    by_ot[n_ot] += 1
    if bad:
        unknown_games.append((contest.get("id"), day, ",".join(seen)))
    elif n_ot and len(examples[n_ot]) < 4:
        examples[n_ot].append(
            (contest.get("id"), day, ",".join(seen),
             contest.get("currentPeriod")))

out("distinct period labels seen (label -> how many times)")
for lab, n in sorted(labels.items(), key=lambda kv: (-kv[1], kv[0])):
    flag = "   <- NOT RECOGNISED" if lab in unknown_labels else ""
    out(f"  {lab!r:10} {n}{flag}")
out()

out("games by recognised overtime periods")
for n in sorted(by_ot):
    kind = "regulation" if n == 0 else f"{n}OT"
    out(f"  {n} OT   {by_ot[n]:>6}   {kind}")
if no_linescore:
    out(f"  no linescore {len(no_linescore):>6}   (e.g. {no_linescore[:5]})")
out()

if unknown_games:
    out(f"GAMES WITH UNRECOGNISED LABELS: {len(unknown_games)}")
    out("  The scraper EXCLUDES these periods rather than guessing, so these")
    out("  games' halves+OT will not sum to the boxscore total. Send this list")
    out("  and the labels can be added to classify_period().")
    for gid, day, seen in unknown_games[:10]:
        out(f"  game {gid}  {day}  periods=[{seen}]")
    if len(unknown_games) > 10:
        out(f"  ... and {len(unknown_games) - 10} more")
    out()

if examples:
    out("overtime examples")
    for n in sorted(examples):
        for gid, day, seen, disp in examples[n]:
            out(f"  {n}OT  game {gid}  {day}  periods=[{seen}]  "
                f"currentPeriod={disp!r}")
else:
    out("NO overtime games found in this cache.")
out()

if days:
    out(f"dates covered: {min(days)} .. {max(days)}")

with open("period_audit.txt", "w", encoding="utf-8") as fh:
    fh.write("\n".join(_lines))

print()
print("=" * 60)
print(" DONE. Attach period_audit.txt in chat.")
print("=" * 60)
