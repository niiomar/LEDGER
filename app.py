from flask import Flask, jsonify, request, render_template, session
import sqlite3, os, datetime, hmac, secrets
from contextlib import closing
from config import SECRET_KEY, ADMIN_PASSWORD, DB_PATH
from auth import login_required

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
# Not forcing SESSION_COOKIE_SECURE: this app is served over plain HTTP on
# the local network by default, and a Secure cookie would silently stop
# being sent, breaking login. Turn it on if you put this behind HTTPS.
DB = DB_PATH

MONTHS = ["January","February","March","April","May","June",
          "July","August","September","October","November","December"]

def month_to_int(s):
    parts = s.strip().split()
    return int(parts[1]) * 12 + MONTHS.index(parts[0])

def int_to_month(n):
    return f"{MONTHS[n % 12]} {n // 12}"

MAX_AMOUNT = 1_000_000
MAX_NAME_LEN = 200
MAX_TEXT_LEN = 500

def parse_positive_amount(value):
    """Returns a positive float within a sane bound, or None otherwise."""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    return amount if 0 < amount <= MAX_AMOUNT else None

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with closing(get_db()) as conn, conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS dues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
            amount REAL NOT NULL,
            period_from TEXT NOT NULL,
            period_to TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL CHECK(type IN ('Credit','Debit')),
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            date TEXT NOT NULL,
            note TEXT DEFAULT '',
            dues_id INTEGER REFERENCES dues(id) ON DELETE CASCADE,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE INDEX IF NOT EXISTS idx_dues_member_id ON dues(member_id);
        CREATE INDEX IF NOT EXISTS idx_ledger_date ON ledger(date);
        """)
        cols = [r['name'] for r in conn.execute("PRAGMA table_info(ledger)").fetchall()]
        if 'dues_id' not in cols:
            conn.execute("ALTER TABLE ledger ADD COLUMN dues_id INTEGER REFERENCES dues(id) ON DELETE CASCADE")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_dues_id ON ledger(dues_id)")

def merge_dues_for_member(conn, member_id):
    rows = conn.execute(
        "SELECT id, amount, period_from, period_to FROM dues WHERE member_id=? ORDER BY period_from",
        (member_id,)
    ).fetchall()

    if len(rows) < 2:
        return

    intervals = []
    for r in rows:
        try:
            f = month_to_int(r['period_from'])
            t = month_to_int(r['period_to'])
            intervals.append({'id': r['id'], 'from': f, 'to': t, 'amount': r['amount']})
        except Exception:
            return  

    intervals.sort(key=lambda x: x['from'])

    merged = [intervals[0].copy()]
    for cur in intervals[1:]:
        prev = merged[-1]
        if cur['from'] <= prev['to'] + 1:  
            prev['to'] = max(prev['to'], cur['to'])
            prev['amount'] += cur['amount']
            prev['merged_ids'] = prev.get('merged_ids', [prev['id']]) + [cur['id']]
        else:
            merged.append(cur.copy())

    all_orig_ids = [r['id'] for r in intervals]
    if len(merged) == len(intervals):
        return

    # Re-point ledger rows at the new merged dues id before dropping the old
    # rows, otherwise ledger.dues_id's ON DELETE CASCADE would wipe out the
    # cash entries that funded this coverage period.
    for m in merged:
        orig_ids = m.get('merged_ids', [m['id']])
        cur = conn.execute(
            "INSERT INTO dues(member_id, amount, period_from, period_to) VALUES(?,?,?,?)",
            (member_id, round(m['amount'], 2), int_to_month(m['from']), int_to_month(m['to']))
        )
        new_id = cur.lastrowid
        placeholders = ','.join('?' * len(orig_ids))
        conn.execute(
            f"UPDATE ledger SET dues_id=? WHERE dues_id IN ({placeholders})",
            (new_id, *orig_ids)
        )

    for rid in all_orig_ids:
        conn.execute("DELETE FROM dues WHERE id=?", (rid,))


def seed_data():
    with closing(get_db()) as conn, conn:
        if conn.execute("SELECT COUNT(*) FROM members").fetchone()[0] > 0:
            return

        members = [
            "JASON NII OMAN MENSAH","FELICIA KUSI","FRANCIS ADUFUL","ERNEST OFORI ADDO",
            "RANSFORD ABOAGYE","JOSEPH DZREKE","STEPHEN BOAMAH","NADIA BOAMAH","ENOCK QUAYE",
            "BENEDICT APPIAH","INUSAH GANIYU","STEPHEN GASSONU","JONES YEBOAH","ROBERTA ABBAN",
            "BELINDA BUAH","RACHEAL AGBALE","MORGAN FRANCIS","GLAVEE BETTY","WILFRED AKULGA",
            "CALEB DARKO","GIFTY AGYEKUM","DAVID DOE NYAMORDEY","ANDREWS AMOFAH ADJEI",
            "MR BENJAMIN","GEORGE AMANORTSU","EMELIA COFFIE","TAHIR AHMED"
        ]
        for m in members:
            conn.execute("INSERT OR IGNORE INTO members(name) VALUES(?)", (m,))

        dues_data = [
            ("JOSEPH DZREKE",       160, "October 2024",  "May 2025"),
            ("STEPHEN BOAMAH",       60, "October 2024",  "December 2024"),
            ("ERNEST OFORI ADDO",   140, "October 2024",  "April 2025"),
            ("JASON NII OMAN MENSAH",400,"October 2024",  "May 2026"),
            ("NADIA BOAMAH",        120, "October 2024",  "March 2025"),
            ("FRANCIS ADUFUL",      180, "October 2024",  "June 2025"),
            ("FRANCIS ADUFUL",      100, "July 2025",     "November 2025"),
            ("FELICIA KUSI",         80, "October 2024",  "January 2025"),
            ("RANSFORD ABOAGYE",    100, "October 2024",  "February 2025"),
            ("TAHIR AHMED",         320, "October 2024",  "January 2026"),
            ("MORGAN FRANCIS",      120, "December 2024", "May 2025"),
            ("RACHEAL AGBALE",      260, "November 2024", "November 2025"),
            ("GLAVEE BETTY",         20, "November 2024", "November 2024"),
            ("ENOCK QUAYE",         100, "April 2025",    "August 2025"),
            ("BENEDICT APPIAH",      40, "April 2025",    "May 2025"),
            ("INUSAH GANIYU",       120, "March 2025",    "August 2025"),
            ("STEPHEN GASSONU",     180, "January 2025",  "September 2025"),
            ("DAVID DOE NYAMORDEY",  60, "April 2025",    "June 2025"),
            ("JONES YEBOAH",         20, "June 2025",     "June 2025"),
            ("ROBERTA ABBAN",       240, "June 2025",     "May 2026"),
            ("BELINDA BUAH",        100, "January 2025",  "May 2025"),
            ("WILFRED AKULGA",      100, "October 2024",  "February 2025"),
            ("CALEB DARKO",          20, "April 2025",    "April 2025"),
            ("GIFTY AGYEKUM",       100, "October 2024",  "February 2025"),
            ("ANDREWS AMOFAH ADJEI", 20, "October 2025",  "October 2025"),
            ("GEORGE AMANORTSU",    120, "October 2025",  "March 2026"),
            ("EMELIA COFFIE",        40, "March 2026",    "April 2026"),
        ]
        for name, amount, frm, to in dues_data:
            row = conn.execute("SELECT id FROM members WHERE name=?", (name,)).fetchone()
            if row:
                conn.execute(
                    "INSERT INTO dues(member_id,amount,period_from,period_to) VALUES(?,?,?,?)",
                    (row['id'], amount, frm, to)
                )

        francis = conn.execute("SELECT id FROM members WHERE name='FRANCIS ADUFUL'").fetchone()
        if francis:
            merge_dues_for_member(conn, francis['id'])

        ledger_data = [
            ("Debit",  "Batteries",            68,  "2025-03-23", ""),
            ("Debit",  "Batteries",           100,  "2025-04-06", ""),
            ("Debit",  "Batteries",            68,  "2025-04-20", ""),
            ("Credit", "Dues",                220,  "2025-04-20", ""),
            ("Debit",  "Batteries",            68,  "2025-05-07", ""),
            ("Credit", "Dues",                320,  "2025-05-18", ""),
            ("Debit",  "Batteries (2)",       136,  "2025-05-28", ""),
            ("Credit", "Dues",                 60,  "2025-06-01", ""),
            ("Credit", "Dues",                 60,  "2025-06-08", ""),
            ("Credit", "Dues",                120,  "2025-06-10", ""),
            ("Credit", "Dues",                120,  "2025-06-15", ""),
            ("Credit", "Dues",                 60,  "2025-06-19", ""),
            ("Debit",  "Splitter (Projection)",200, "2025-06-21", ""),
            ("Debit",  "Seed Offering",       200,  "2025-06-22", ""),
            ("Credit", "Dues",                120,  "2025-06-29", ""),
            ("Credit", "Dues",                100,  "2025-07-01", ""),
            ("Credit", "Dues",                 20,  "2025-07-12", ""),
            ("Credit", "Dues",                100,  "2025-07-14", ""),
            ("Credit", "Dues",                140,  "2025-10-05", ""),
            ("Credit", "Dues",                120,  "2025-10-12", ""),
            ("Credit", "Dues",                100,  "2025-10-19", ""),
            ("Credit", "Dues",                200,  "2026-04-05", ""),
            ("Credit", "Dues",                230,  "2026-04-11", ""),
            ("Credit", "Dues",                300,  "2026-05-24", ""),
        ]
        for typ, desc, amt, date, note in ledger_data:
            conn.execute(
                "INSERT INTO ledger(type,description,amount,date,note) VALUES(?,?,?,?,?)",
                (typ, desc, amt, date, note)
            )

@app.route('/api/members', methods=['GET'])
def get_members():
    with closing(get_db()) as conn, conn:
        rows = conn.execute("SELECT * FROM members ORDER BY name").fetchall()
        return jsonify([dict(r) for r in rows])

@app.route('/api/members', methods=['POST'])
@login_required
def add_member():
    data = request.json
    name = (data.get('name') or '').strip().upper()
    if not name:
        return jsonify({'error': 'Name is required'}), 400
    if len(name) > MAX_NAME_LEN:
        return jsonify({'error': f'Name must be {MAX_NAME_LEN} characters or fewer'}), 400
    try:
        with closing(get_db()) as conn, conn:
            cur = conn.execute("INSERT INTO members(name) VALUES(?)", (name,))
            return jsonify({'id': cur.lastrowid, 'name': name}), 201
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Member already exists'}), 409

@app.route('/api/members/<int:mid>', methods=['PUT'])
@login_required
def update_member(mid):
    data = request.json
    name = (data.get('name') or '').strip().upper()
    if not name:
        return jsonify({'error': 'Name is required'}), 400
    if len(name) > MAX_NAME_LEN:
        return jsonify({'error': f'Name must be {MAX_NAME_LEN} characters or fewer'}), 400
    try:
        with closing(get_db()) as conn, conn:
            conn.execute("UPDATE members SET name=? WHERE id=?", (name, mid))
            return jsonify({'id': mid, 'name': name})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Name already taken'}), 409

@app.route('/api/members/<int:mid>', methods=['DELETE'])
@login_required
def delete_member(mid):
    with closing(get_db()) as conn, conn:
        conn.execute("DELETE FROM members WHERE id=?", (mid,))
        return jsonify({'ok': True})

@app.route('/api/dues', methods=['GET'])
def get_dues():
    member_id = request.args.get('member_id')
    with closing(get_db()) as conn, conn:
        if member_id:
            rows = conn.execute("""
                SELECT d.*, m.name as member_name
                FROM dues d JOIN members m ON d.member_id=m.id
                WHERE d.member_id=? ORDER BY d.period_from ASC
            """, (member_id,)).fetchall()
        else:
            rows = conn.execute("""
                SELECT d.*, m.name as member_name
                FROM dues d JOIN members m ON d.member_id=m.id
                ORDER BY d.id DESC
            """).fetchall()
        return jsonify([dict(r) for r in rows])

@app.route('/api/dues', methods=['POST'])
@login_required
def add_dues():
    data = request.json
    try:
        member_id = int(data.get('member_id'))
    except (TypeError, ValueError):
        member_id = None
    amount      = parse_positive_amount(data.get('amount'))
    period_from = (data.get('period_from') or '').strip()
    period_to   = (data.get('period_to')   or '').strip()
    if not member_id or amount is None or not period_from or not period_to:
        return jsonify({'error': 'All fields required'}), 400

    with closing(get_db()) as conn, conn:
        member = conn.execute("SELECT name FROM members WHERE id=?", (member_id,)).fetchone()
        if not member:
            return jsonify({'error': 'Member not found'}), 404

        cur = conn.execute(
            "INSERT INTO dues(member_id,amount,period_from,period_to) VALUES(?,?,?,?)",
            (member_id, amount, period_from, period_to)
        )
        dues_id = cur.lastrowid

        today = datetime.date.today().isoformat()
        desc  = f"Dues – {member['name']}"
        note  = f"{period_from} → {period_to}"
        conn.execute(
            "INSERT INTO ledger(type,description,amount,date,note,dues_id) VALUES(?,?,?,?,?,?)",
            ('Credit', desc, amount, today, note, dues_id)
        )

        merge_dues_for_member(conn, member_id)

        rows = conn.execute("""
            SELECT d.*, m.name as member_name FROM dues d
            JOIN members m ON d.member_id=m.id WHERE d.member_id=?
            ORDER BY d.period_from ASC
        """, (member_id,)).fetchall()
        return jsonify([dict(r) for r in rows]), 201

@app.route('/api/dues/<int:did>', methods=['PUT'])
@login_required
def update_dues(did):
    data = request.json
    amount      = parse_positive_amount(data.get('amount'))
    period_from = (data.get('period_from') or '').strip()
    period_to   = (data.get('period_to')   or '').strip()
    if amount is None or not period_from or not period_to:
        return jsonify({'error': 'amount, period_from, and period_to are required'}), 400

    with closing(get_db()) as conn, conn:
        row = conn.execute("SELECT member_id FROM dues WHERE id=?", (did,)).fetchone()
        if not row:
            return jsonify({'error': 'Dues record not found'}), 404
        member_id = row['member_id']
        conn.execute(
            "UPDATE dues SET amount=?, period_from=?, period_to=? WHERE id=?",
            (amount, period_from, period_to, did)
        )

        # A dues record can fund more than one ledger entry once periods have
        # been merged (merge_dues_for_member). Only sync the amount back down
        # when there's exactly one linked payment to avoid overwriting
        # multiple real cash entries with one new total; always refresh the
        # note so displayed coverage periods stay current.
        note = f"{period_from} → {period_to}"
        linked = conn.execute("SELECT id FROM ledger WHERE dues_id=?", (did,)).fetchall()
        if len(linked) == 1:
            conn.execute("UPDATE ledger SET amount=?, note=? WHERE id=?", (amount, note, linked[0]['id']))
        elif linked:
            conn.execute("UPDATE ledger SET note=? WHERE dues_id=?", (note, did))

        merge_dues_for_member(conn, member_id)
        rows = conn.execute("""
            SELECT d.*, m.name as member_name FROM dues d
            JOIN members m ON d.member_id=m.id WHERE d.member_id=?
            ORDER BY d.period_from ASC
        """, (member_id,)).fetchall()
        return jsonify([dict(r) for r in rows])

@app.route('/api/dues/<int:did>', methods=['DELETE'])
@login_required
def delete_dues(did):
    # ledger.dues_id is ON DELETE CASCADE, so any ledger entries funding this
    # coverage record are removed automatically along with it.
    with closing(get_db()) as conn, conn:
        conn.execute("DELETE FROM dues WHERE id=?", (did,))
        return jsonify({'ok': True})

@app.route('/api/ledger', methods=['GET'])
def get_ledger():
    date_from = request.args.get('date_from', '')
    date_to   = request.args.get('date_to', '')
    keyword   = request.args.get('keyword', '')
    tx_type   = request.args.get('type', '')

    query  = "SELECT * FROM ledger WHERE 1=1"
    params = []
    if date_from:
        query += " AND date >= ?"; params.append(date_from)
    if date_to:
        query += " AND date <= ?"; params.append(date_to)
    if keyword:
        query += " AND (description LIKE ? OR note LIKE ?)"; params += [f'%{keyword}%', f'%{keyword}%']
    if tx_type in ('Credit', 'Debit'):
        query += " AND type = ?"; params.append(tx_type)
    query += " ORDER BY date ASC, id ASC"

    with closing(get_db()) as conn, conn:
        rows = conn.execute(query, params).fetchall()
        result = []
        balance = 0
        for r in rows:
            balance += r['amount'] if r['type'] == 'Credit' else -r['amount']
            d = dict(r); d['running_balance'] = round(balance, 2)
            result.append(d)
        return jsonify(result[::-1])

@app.route('/api/ledger/summary', methods=['GET'])
def ledger_summary():
    with closing(get_db()) as conn, conn:
        credits     = conn.execute("SELECT COALESCE(SUM(amount),0) as s FROM ledger WHERE type='Credit'").fetchone()['s']
        debits      = conn.execute("SELECT COALESCE(SUM(amount),0) as s FROM ledger WHERE type='Debit'").fetchone()['s']
        
        # Dues total = actual cash receipts in the ledger that are linked to a
        # dues coverage record, not a string match on the description.
        dues_total  = conn.execute("SELECT COALESCE(SUM(amount),0) as s FROM ledger WHERE type='Credit' AND dues_id IS NOT NULL").fetchone()['s']
        
        member_count= conn.execute("SELECT COUNT(*) as c FROM members").fetchone()['c']
        dues_count  = conn.execute("SELECT COUNT(*) as c FROM dues").fetchone()['c']
        ledger_count= conn.execute("SELECT COUNT(*) as c FROM ledger").fetchone()['c']
        return jsonify({
            'balance':       round(credits - debits, 2),
            'total_credits': round(credits, 2),
            'total_debits':  round(debits, 2),
            'total_dues':    round(dues_total, 2),
            'member_count':  member_count,
            'dues_count':    dues_count,
            'ledger_count':  ledger_count,
        })

@app.route('/api/ledger', methods=['POST'])
@login_required
def add_ledger():
    data = request.json
    typ  = data.get('type')
    desc = (data.get('description') or '').strip()
    amount = parse_positive_amount(data.get('amount'))
    date   = (data.get('date') or '').strip()
    note   = (data.get('note') or '').strip()
    if typ not in ('Credit', 'Debit') or not desc or amount is None or not date:
        return jsonify({'error': 'type, description, amount, and date are required'}), 400
    if len(desc) > MAX_TEXT_LEN or len(note) > MAX_TEXT_LEN:
        return jsonify({'error': f'Description and note must be {MAX_TEXT_LEN} characters or fewer'}), 400
    with closing(get_db()) as conn, conn:
        cur = conn.execute(
            "INSERT INTO ledger(type,description,amount,date,note) VALUES(?,?,?,?,?)",
            (typ, desc, amount, date, note)
        )
        row = conn.execute("SELECT * FROM ledger WHERE id=?", (cur.lastrowid,)).fetchone()
        return jsonify(dict(row)), 201

@app.route('/api/ledger/<int:lid>', methods=['PUT'])
@login_required
def update_ledger(lid):
    data = request.json
    typ  = data.get('type')
    desc = (data.get('description') or '').strip()
    amount = parse_positive_amount(data.get('amount'))
    date   = (data.get('date') or '').strip()
    note   = (data.get('note') or '').strip()
    if typ not in ('Credit', 'Debit') or not desc or amount is None or not date:
        return jsonify({'error': 'type, description, amount, and date are required'}), 400
    if len(desc) > MAX_TEXT_LEN or len(note) > MAX_TEXT_LEN:
        return jsonify({'error': f'Description and note must be {MAX_TEXT_LEN} characters or fewer'}), 400
    with closing(get_db()) as conn, conn:
        conn.execute(
            "UPDATE ledger SET type=?, description=?, amount=?, date=?, note=? WHERE id=?",
            (typ, desc, amount, date, note, lid)
        )
        row = conn.execute("SELECT * FROM ledger WHERE id=?", (lid,)).fetchone()
        if row['dues_id']:
            total = conn.execute(
                "SELECT COALESCE(SUM(amount),0) as s FROM ledger WHERE dues_id=?", (row['dues_id'],)
            ).fetchone()['s']
            conn.execute("UPDATE dues SET amount=? WHERE id=?", (round(total, 2), row['dues_id']))
        return jsonify(dict(row))

@app.route('/api/ledger/<int:lid>', methods=['DELETE'])
@login_required
def delete_ledger(lid):
    with closing(get_db()) as conn, conn:
        row = conn.execute("SELECT dues_id FROM ledger WHERE id=?", (lid,)).fetchone()
        conn.execute("DELETE FROM ledger WHERE id=?", (lid,))
        if row and row['dues_id']:
            remaining = conn.execute(
                "SELECT COALESCE(SUM(amount),0) as s FROM ledger WHERE dues_id=?", (row['dues_id'],)
            ).fetchone()['s']
            if remaining <= 0:
                conn.execute("DELETE FROM dues WHERE id=?", (row['dues_id'],))
            else:
                conn.execute("UPDATE dues SET amount=? WHERE id=?", (round(remaining, 2), row['dues_id']))
        return jsonify({'ok': True})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = str(data.get('username') or '')
    password = str(data.get('password') or '')
    if username == "admin" and hmac.compare_digest(password, ADMIN_PASSWORD):
        session['authenticated'] = True
        session['csrf_token'] = secrets.token_hex(32)
        return jsonify({'ok': True, 'csrf_token': session['csrf_token']})
    return jsonify({'error': 'Invalid username or password'}), 401


@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop('authenticated', None)
    session.pop('csrf_token', None)
    return jsonify({'ok': True})

@app.route('/api/session', methods=['GET'])
def get_session():
    if not session.get('authenticated'):
        return jsonify({'authenticated': False})
    if not session.get('csrf_token'):
        session['csrf_token'] = secrets.token_hex(32)
    return jsonify({'authenticated': True, 'csrf_token': session['csrf_token']})

@app.route('/api/reports/monthly', methods=['GET'])
def monthly_report():
    month = request.args.get('month')
    if not month:
        return jsonify({'error': 'Month is required'}), 400

    with closing(get_db()) as conn, conn:
        ledger = conn.execute("""
            SELECT l.*, m.name as dues_member_name, d.period_from as dues_period_from, d.period_to as dues_period_to
            FROM ledger l
            LEFT JOIN dues d ON l.dues_id = d.id
            LEFT JOIN members m ON d.member_id = m.id
            WHERE strftime('%Y-%m', l.date) = ?
            ORDER BY l.date ASC
        """, (month,)).fetchall()

        dues_list = []
        general_ledger = []
        for r in ledger:
            if r['dues_id'] is not None:
                dues_list.append({
                    'created_at': r['date'],
                    'member_name': r['dues_member_name'],
                    'period_from': r['dues_period_from'],
                    'period_to': r['dues_period_to'],
                    'amount': r['amount']
                })
            else:
                general_ledger.append({k: r[k] for k in ('id','type','description','amount','date','note','dues_id','created_at')})

        summary = {
            'credits':      sum(r['amount'] for r in ledger if r['type'] == 'Credit'),
            'debits':       sum(r['amount'] for r in ledger if r['type'] == 'Debit'),
            'dues':         sum(d['amount'] for d in dues_list),
            'count_ledger': len(general_ledger),
            'count_dues':   len(dues_list)
        }

        return jsonify({
            'month':   month,
            'ledger':  general_ledger,
            'dues':    dues_list,
            'summary': summary
        })

@app.route('/api/reports/comprehensive', methods=['GET'])
def comprehensive_report():
    with closing(get_db()) as conn, conn:
        ledger = conn.execute("""
            SELECT l.*, m.name as dues_member_name, d.period_from as dues_period_from, d.period_to as dues_period_to
            FROM ledger l
            LEFT JOIN dues d ON l.dues_id = d.id
            LEFT JOIN members m ON d.member_id = m.id
            ORDER BY l.date ASC
        """).fetchall()

        dues_list = []
        general_ledger = []
        for r in ledger:
            if r['dues_id'] is not None:
                dues_list.append({
                    'created_at': r['date'],
                    'member_name': r['dues_member_name'],
                    'period_from': r['dues_period_from'],
                    'period_to': r['dues_period_to'],
                    'amount': r['amount']
                })
            else:
                general_ledger.append({k: r[k] for k in ('id','type','description','amount','date','note','dues_id','created_at')})

        summary = {
            'credits':      sum(r['amount'] for r in ledger if r['type'] == 'Credit'),
            'debits':       sum(r['amount'] for r in ledger if r['type'] == 'Debit'),
            'dues':         sum(d['amount'] for d in dues_list),
            'count_ledger': len(general_ledger),
            'count_dues':   len(dues_list)
        }

        return jsonify({
            'month':   'All-Time Comprehensive',
            'ledger':  general_ledger,
            'dues':    dues_list,
            'summary': summary
        })

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    init_db()
    seed_data()
    if SECRET_KEY == "dev-only-change-me" or ADMIN_PASSWORD in ("admin", "change-me"):
        print("\n  WARNING: SECRET_KEY and/or ADMIN_PASSWORD are still set to their")
        print("  insecure defaults. Anyone on your network can log in and the")
        print("  session cookie can be forged. Set real values in your .env file.\n")
    print("\n  GMM Kasoa Media System running at http://127.0.0.1:5000\n")
    app.run(debug=False, host='0.0.0.0', port=5000)