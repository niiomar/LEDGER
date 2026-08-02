import hmac
from functools import wraps
from flask import session, jsonify, request

UNSAFE_METHODS = ("POST", "PUT", "PATCH", "DELETE")


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("authenticated"):
            return jsonify({"error": "Authentication required"}), 401
        if request.method in UNSAFE_METHODS:
            sent_token = request.headers.get("X-CSRF-Token", "")
            session_token = session.get("csrf_token", "")
            if not session_token or not hmac.compare_digest(sent_token, session_token):
                return jsonify({"error": "Invalid or missing CSRF token"}), 403
        return f(*args, **kwargs)
    return wrapper
