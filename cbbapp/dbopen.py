"""Shared read-only cache opener for the audit scripts.

scrape_full.py now runs the cache in WAL mode, and a URI "mode=ro" connection
to a WAL database needs to touch the -shm sidecar file. When that is not
possible -- a locked-down folder, a sidecar owned by the running scrape,
OneDrive syncing the file -- SQLite raises rather than falling back, so try
the strict read-only open first and settle for a normal one if it fails.
Nothing here ever writes.
"""

import sqlite3


def open_readonly(path):
    """-> sqlite3.Connection, or raise SystemExit with a readable message."""
    attempts = [
        (f"file:{path}?mode=ro", {"uri": True}),
        (path, {}),
    ]
    problems = []
    for target, kwargs in attempts:
        try:
            conn = sqlite3.connect(target, timeout=30.0, **kwargs)
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone()
            return conn
        except sqlite3.Error as exc:
            problems.append(f"{type(exc).__name__}: {exc}")

    raise SystemExit(
        f"Could not open {path}\n"
        + "\n".join(f"  - {p}" for p in problems)
        + "\n\nRun this from the folder that holds the .db file, and check "
          "that the name is right (default: ncaab_raw.db)."
    )


def tables(conn):
    return {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}


def count(conn, table):
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except sqlite3.OperationalError:
        return None


def season_of(day):
    """"2025-26" from "2025-11-09". None for anything unparseable."""
    try:
        year, month = int(str(day)[:4]), int(str(day)[5:7])
    except (TypeError, ValueError):
        return None
    return f"{year}-{str(year + 1)[-2:]}" if month >= 7 \
        else f"{year - 1}-{str(year)[-2:]}"
