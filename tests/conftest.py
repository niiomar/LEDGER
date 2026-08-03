import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

import app as app_module


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(app_module, "DB", db_path)
    app_module.init_db()
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


@pytest.fixture
def auth(client):
    """Logs in and returns (client, csrf_token)."""
    resp = client.post(
        "/api/login",
        json={"username": "admin", "password": app_module.ADMIN_PASSWORD},
    )
    assert resp.status_code == 200
    return client, resp.get_json()["csrf_token"]


def post_json(client, token, url, payload):
    return client.post(url, json=payload, headers={"X-CSRF-Token": token})


def put_json(client, token, url, payload):
    return client.put(url, json=payload, headers={"X-CSRF-Token": token})


def delete_json(client, token, url):
    return client.delete(url, headers={"X-CSRF-Token": token})


def add_member(client, token, name="TEST MEMBER"):
    resp = post_json(client, token, "/api/members", {"name": name})
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["id"]
