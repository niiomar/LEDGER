"""
One-time data correction migration.

This was previously baked into app.py's startup sequence (migrate_data()),
running on every app launch indefinitely. That's fragile and confusing —
once these corrections have been applied to your database, they should
never need to run again.

Run once:
    python migrations/001_data_corrections.py

After running successfully, this file can be deleted or archived.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import DB_PATH
import sqlite3
from contextlib import closing


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def month_to_int(s):
    MONTHS = ["January","February","March","April","May","June",
              "July","August","September","October","November","December"]
    parts = s.strip().split()
    return int(parts[1]) * 12 + MONTHS.index(parts[0])


def int_to_month(n):
    MONTHS = ["January","February","March","April","May","June",
              "July","August","September","October","November","December"]
    return f"{MONTHS[n % 12]} {n // 12}"


def merge_dues_for_member(conn, member_id):
    rows = conn.execute(
        "SELECT id, amount, period_from, period_to FROM dues WHERE member_id=? ORDER BY period_from",
        (member_id,)
    ).fetchall()
    if len(rows) < 2:
        return

    intervals = []
    for r in rows:
        f = month_to_int(r['period_from'])
        t = month_to_int(r['period_to'])
        intervals.append({'id': r['id'], 'from': f, 'to': t, 'amount': r['amount']})
    intervals.sort(key=lambda x: x['from'])

    merged = [intervals[0].copy()]
    for cur in intervals[1:]:
        prev = merged[-1]
        if cur['from'] <= prev['to'] + 1:
            prev['to'] = max(prev['to'], cur['to'])
            prev['amount'] += cur['amount']
        else:
            merged.append(cur.copy())

    if len(merged) == len(intervals):
        return

    for r in intervals:
        conn.execute("DELETE FROM dues WHERE id=?", (r['id'],))
    for m in merged:
        conn.execute(
            "INSERT INTO dues(member_id, amount, period_from, period_to) VALUES(?,?,?,?)",
            (member_id, round(m['amount'], 2), int_to_month(m['from']), int_to_month(m['to']))
        )


def run():
    with closing(get_db()) as conn, conn:
        conn.execute("""
            UPDATE dues SET period_to = 'June 2025'
            WHERE period_from = 'October 2024' AND period_to = 'September 2025' AND amount = 180
              AND member_id = (SELECT id FROM members WHERE name = 'FRANCIS ADUFUL')
        """)
        conn.execute("""
            UPDATE dues SET period_from = 'July 2025', period_to = 'November 2025'
            WHERE period_from = 'October 2025' AND period_to = 'February 2026' AND amount = 100
              AND member_id = (SELECT id FROM members WHERE name = 'FRANCIS ADUFUL')
        """)

        francis = conn.execute("SELECT id FROM members WHERE name='FRANCIS ADUFUL'").fetchone()
        if francis:
            merge_dues_for_member(conn, francis['id'])

        conn.execute("DELETE FROM ledger WHERE description LIKE '%Correction%' OR description LIKE '%Restore%'")

        conn.execute("INSERT OR IGNORE INTO members(name) VALUES('JASON NII OMAN MENSAH')")
        jason = conn.execute("SELECT id FROM members WHERE name='JASON NII OMAN MENSAH'").fetchone()
        if jason:
            j_id = jason['id']
            conn.execute("DELETE FROM dues WHERE member_id=? AND amount IN (20, 420)", (j_id,))
            has_dues = conn.execute("SELECT COUNT(*) as c FROM dues WHERE member_id=? AND amount=400", (j_id,)).fetchone()['c']
            if has_dues == 0:
                conn.execute("INSERT INTO dues(member_id, amount, period_from, period_to) VALUES(?,?,?,?)",
                             (j_id, 400, 'October 2024', 'May 2026'))
            conn.execute("DELETE FROM ledger WHERE description LIKE '%JASON%' AND amount IN (20, 400, 420)")

    print("Migration 001 complete.")


if __name__ == "__main__":
    run()
