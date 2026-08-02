"""
One-time data migration: link existing "Dues" ledger entries to their
matching dues coverage record via the new ledger.dues_id column.

Before this migration, a ledger row created for a dues payment was only
associated with its dues record by convention (description started with
"Dues – <name>", period stashed as text in `note`). Reports and the dues
total reconstructed that link by string-matching, which silently
miscategorized any manual "Dues..." ledger entry and let the two tables
drift out of sync whenever a dues record was edited or deleted. app.py now
sets dues_id explicitly going forward; this migration backfills it for
entries created under the old convention.

Rows whose dues record has since been merged (merge_dues_for_member changes
period/amount and swaps in a new id) won't match by the original values and
are left unlinked — they'll keep showing as general ledger entries in
reports until relinked by hand.

Run once:
    python migrations/002_link_ledger_to_dues.py

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


def run():
    with closing(get_db()) as conn, conn:
        cols = [r['name'] for r in conn.execute("PRAGMA table_info(ledger)").fetchall()]
        if 'dues_id' not in cols:
            conn.execute("ALTER TABLE ledger ADD COLUMN dues_id INTEGER REFERENCES dues(id) ON DELETE CASCADE")

        candidates = conn.execute("""
            SELECT id, description, amount, note FROM ledger
            WHERE type='Credit' AND description LIKE 'Dues%' AND dues_id IS NULL
        """).fetchall()

        linked, skipped = 0, 0
        for row in candidates:
            name = row['description'].replace('Dues – ', '').replace('Dues - ', '').strip()
            parts = (row['note'] or '').split(' → ')
            if len(parts) != 2:
                skipped += 1
                continue
            period_from, period_to = parts[0].strip(), parts[1].strip()

            dues_row = conn.execute("""
                SELECT d.id FROM dues d JOIN members m ON d.member_id = m.id
                WHERE m.name = ? AND d.period_from = ? AND d.period_to = ? AND d.amount = ?
            """, (name, period_from, period_to, row['amount'])).fetchone()

            if dues_row:
                conn.execute("UPDATE ledger SET dues_id=? WHERE id=?", (dues_row['id'], row['id']))
                linked += 1
            else:
                skipped += 1

        print(f"Migration 002 complete. Linked {linked} ledger entries to dues records, "
              f"{skipped} left unlinked (no exact match — likely a merged period; link by hand if needed).")


if __name__ == "__main__":
    run()
