from conftest import add_member, delete_json, post_json, put_json


# --- Auth / CSRF ---

def test_login_rejects_wrong_password(client):
    resp = client.post("/api/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


def test_login_accepts_correct_password(auth):
    client, token = auth
    assert token


def test_write_requires_auth(client):
    resp = client.post("/api/members", json={"name": "X"})
    assert resp.status_code == 401


def test_write_requires_csrf_token(auth):
    client, _token = auth
    resp = client.post("/api/members", json={"name": "X"})
    assert resp.status_code == 403


def test_write_rejects_wrong_csrf_token(auth):
    client, _token = auth
    resp = post_json(client, "not-the-real-token", "/api/members", {"name": "X"})
    assert resp.status_code == 403


def test_session_endpoint_reflects_login_state(client):
    resp = client.get("/api/session")
    assert resp.get_json() == {"authenticated": False}

    client.post("/api/login", json={"username": "admin", "password": _admin_password()})
    resp = client.get("/api/session")
    data = resp.get_json()
    assert data["authenticated"] is True
    assert data["csrf_token"]


def test_logout_invalidates_session(auth):
    client, token = auth
    client.post("/api/logout")
    resp = post_json(client, token, "/api/members", {"name": "X"})
    assert resp.status_code == 401


# --- Members ---

def test_add_member_then_list(auth):
    client, token = auth
    add_member(client, token, "Jane Doe")
    resp = client.get("/api/members")
    names = [m["name"] for m in resp.get_json()]
    assert "JANE DOE" in names  # names are upper-cased server-side


def test_add_duplicate_member_conflicts(auth):
    client, token = auth
    add_member(client, token, "Dup Member")
    resp = post_json(client, token, "/api/members", {"name": "Dup Member"})
    assert resp.status_code == 409


def test_add_member_rejects_overlong_name(auth):
    client, token = auth
    resp = post_json(client, token, "/api/members", {"name": "X" * 201})
    assert resp.status_code == 400


# --- Ledger input validation ---

def test_ledger_rejects_non_numeric_amount(auth):
    client, token = auth
    resp = post_json(client, token, "/api/ledger", {
        "type": "Credit", "description": "Test", "amount": "abc", "date": "2026-01-01",
    })
    assert resp.status_code == 400


def test_ledger_rejects_amount_over_max(auth):
    client, token = auth
    resp = post_json(client, token, "/api/ledger", {
        "type": "Credit", "description": "Test", "amount": 1_000_001, "date": "2026-01-01",
    })
    assert resp.status_code == 400


def test_ledger_rejects_overlong_description(auth):
    client, token = auth
    resp = post_json(client, token, "/api/ledger", {
        "type": "Credit", "description": "X" * 501, "amount": 10, "date": "2026-01-01",
    })
    assert resp.status_code == 400


def test_ledger_rejects_negative_amount(auth):
    client, token = auth
    resp = post_json(client, token, "/api/ledger", {
        "type": "Credit", "description": "Test", "amount": -5, "date": "2026-01-01",
    })
    assert resp.status_code == 400


def test_ledger_summary_ignores_manual_entry_that_looks_like_dues(auth):
    """Regression test: a manual ledger entry merely starting with "Dues" must
    not be counted as real dues income just because of its description - only
    entries actually linked via dues_id should count."""
    client, token = auth
    post_json(client, token, "/api/ledger", {
        "type": "Credit", "description": "Dues refund adjustment", "amount": 999, "date": "2026-01-01",
    })
    summary = client.get("/api/ledger/summary").get_json()
    assert summary["total_dues"] == 0


# --- Dues <-> ledger integrity ---

def test_add_dues_creates_linked_ledger_entry(auth):
    client, token = auth
    mid = add_member(client, token, "Dues Person")
    resp = post_json(client, token, "/api/dues", {
        "member_id": mid, "amount": 50, "period_from": "January 2025", "period_to": "January 2025",
    })
    assert resp.status_code == 201

    summary = client.get("/api/ledger/summary").get_json()
    assert summary["total_dues"] == 50

    ledger = client.get("/api/ledger").get_json()
    dues_rows = [r for r in ledger if r["dues_id"] is not None]
    assert len(dues_rows) == 1
    assert dues_rows[0]["amount"] == 50


def test_adjacent_dues_periods_merge_and_keep_ledger_linked(auth):
    client, token = auth
    mid = add_member(client, token, "Merge Person")
    post_json(client, token, "/api/dues", {
        "member_id": mid, "amount": 20, "period_from": "January 2025", "period_to": "January 2025",
    })
    post_json(client, token, "/api/dues", {
        "member_id": mid, "amount": 20, "period_from": "February 2025", "period_to": "February 2025",
    })

    dues = client.get(f"/api/dues?member_id={mid}").get_json()
    assert len(dues) == 1
    assert dues[0]["period_from"] == "January 2025"
    assert dues[0]["period_to"] == "February 2025"
    assert dues[0]["amount"] == 40

    # Both original ledger entries should still exist and now point at the
    # merged dues record - merging must not lose or orphan cash entries.
    ledger = client.get("/api/ledger").get_json()
    linked = [r for r in ledger if r["dues_id"] == dues[0]["id"]]
    assert len(linked) == 2
    assert sum(r["amount"] for r in linked) == 40


def test_update_dues_syncs_single_linked_ledger_entry(auth):
    client, token = auth
    mid = add_member(client, token, "Update Person")
    add_resp = post_json(client, token, "/api/dues", {
        "member_id": mid, "amount": 30, "period_from": "March 2025", "period_to": "March 2025",
    }).get_json()
    dues_id = add_resp[0]["id"]

    put_json(client, token, f"/api/dues/{dues_id}", {
        "amount": 45, "period_from": "March 2025", "period_to": "March 2025",
    })

    ledger = client.get("/api/ledger").get_json()
    linked = [r for r in ledger if r["dues_id"] == dues_id]
    assert len(linked) == 1
    assert linked[0]["amount"] == 45


def test_update_ledger_amount_recomputes_dues_total(auth):
    client, token = auth
    mid = add_member(client, token, "Ledger Edit Person")
    add_resp = post_json(client, token, "/api/dues", {
        "member_id": mid, "amount": 60, "period_from": "April 2025", "period_to": "April 2025",
    }).get_json()
    dues_id = add_resp[0]["id"]

    ledger = client.get("/api/ledger").get_json()
    ledger_row = next(r for r in ledger if r["dues_id"] == dues_id)

    put_json(client, token, f"/api/ledger/{ledger_row['id']}", {
        "type": "Credit", "description": ledger_row["description"], "amount": 75,
        "date": ledger_row["date"], "note": ledger_row["note"],
    })

    dues = client.get(f"/api/dues?member_id={mid}").get_json()
    assert dues[0]["amount"] == 75


def test_delete_last_linked_ledger_entry_removes_dues_record(auth):
    client, token = auth
    mid = add_member(client, token, "Delete Person")
    add_resp = post_json(client, token, "/api/dues", {
        "member_id": mid, "amount": 25, "period_from": "May 2025", "period_to": "May 2025",
    }).get_json()
    dues_id = add_resp[0]["id"]
    ledger = client.get("/api/ledger").get_json()
    ledger_row = next(r for r in ledger if r["dues_id"] == dues_id)

    delete_json(client, token, f"/api/ledger/{ledger_row['id']}")

    dues = client.get(f"/api/dues?member_id={mid}").get_json()
    assert dues == []


def test_delete_dues_cascades_to_linked_ledger_entry(auth):
    client, token = auth
    mid = add_member(client, token, "Cascade Person")
    add_resp = post_json(client, token, "/api/dues", {
        "member_id": mid, "amount": 15, "period_from": "June 2025", "period_to": "June 2025",
    }).get_json()
    dues_id = add_resp[0]["id"]

    delete_json(client, token, f"/api/dues/{dues_id}")

    ledger = client.get("/api/ledger").get_json()
    assert all(r["dues_id"] != dues_id for r in ledger)


def _admin_password():
    import app as app_module
    return app_module.ADMIN_PASSWORD
