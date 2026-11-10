"""Bind a Dify conversation to its authenticated student and topic."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time


def _signature(payload: str, *, secret: str, student_id: str, course: str, topic_id: str) -> str:
    key = hmac.new(secret.encode(), b"course-coach:dify-conversation:v1", hashlib.sha256).digest()
    scope = json.dumps([student_id, course, topic_id, payload], separators=(",", ":")).encode()
    return hmac.new(key, scope, hashlib.sha256).hexdigest()


def issue_conversation_token(conversation_id: str, **scope: str) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({
        "id": conversation_id, "expires": int(time.time()) + 7 * 86400,
    }, separators=(",", ":")).encode()).decode()
    return f"{payload}.{_signature(payload, **scope)}"


def read_conversation_token(token: str, **scope: str) -> str:
    try:
        payload, signature = token.rsplit(".", 1)
        if not scope["secret"] or not hmac.compare_digest(signature, _signature(payload, **scope)):
            raise ValueError("invalid signature")
        data = json.loads(base64.b64decode(payload, altchars=b"-_", validate=True))
        if not isinstance(data["expires"], int) or data["expires"] <= time.time():
            raise ValueError("expired conversation")
        if not isinstance(data["id"], str) or not 1 <= len(data["id"]) <= 128:
            raise ValueError("invalid conversation")
        return data["id"]
    except (ValueError, KeyError, TypeError, UnicodeError) as exc:
        raise ValueError("invalid conversation token") from exc
