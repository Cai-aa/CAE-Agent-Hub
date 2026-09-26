from __future__ import annotations

import hashlib
import hmac
import json
import re
from typing import Any


# This is the wire-protocol version.  It is intentionally independent from the
# version of bridge.json (the latter remains version 1).
PROTOCOL_VERSION = 3
MAX_REQUEST_BYTES = 1_048_576
MAX_RESPONSE_BYTES = 4_194_304
MAX_HELLO_BYTES = 4_096
AUTH_CHALLENGE_BYTES = 32
SERVER_HELLO_TYPE = "server_hello"
CLIENT_HELLO_TYPE = "client_hello"
REQUEST_TYPE = "request"

_PROOF_RE = re.compile(r"^[0-9a-f]{64}$")
_CHALLENGE_RE = re.compile(r"^[0-9a-f]{64}$")
_SERVER_HELLO_CONTEXT = b"ansa-mcp/server-hello/v3\x00"
_CLIENT_REQUEST_CONTEXT = b"ansa-mcp/client-request/v3\x00"
_SERVER_RESPONSE_CONTEXT = b"ansa-mcp/server-response/v3\x00"


def canonical_json_bytes(value: Any) -> bytes:
    """Return the one deterministic JSON representation used by every proof."""

    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _token_key(token: str) -> bytes:
    if not isinstance(token, str) or len(token) != 64:
        raise ValueError("Bridge token must be 64 hexadecimal characters")
    try:
        key = bytes.fromhex(token)
    except ValueError as exc:
        raise ValueError("Bridge token must be 64 hexadecimal characters") from exc
    if len(key) != 32:
        raise ValueError("Bridge token must encode exactly 32 bytes")
    return key


def authentication_proof(token: str, purpose: str, value: Any) -> str:
    contexts = {
        "server_hello": _SERVER_HELLO_CONTEXT,
        "client_request": _CLIENT_REQUEST_CONTEXT,
        "server_response": _SERVER_RESPONSE_CONTEXT,
    }
    try:
        context = contexts[purpose]
    except KeyError as exc:
        raise ValueError("Unknown authentication proof purpose") from exc
    return hmac.new(
        _token_key(token),
        context + canonical_json_bytes(value),
        hashlib.sha256,
    ).hexdigest()


def proof_matches(token: str, purpose: str, value: Any, proof: Any) -> bool:
    if not isinstance(proof, str) or _PROOF_RE.fullmatch(proof) is None:
        return False
    try:
        expected = authentication_proof(token, purpose, value)
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(proof, expected)


def valid_challenge(value: Any) -> bool:
    return isinstance(value, str) and _CHALLENGE_RE.fullmatch(value) is not None


def server_hello(
    token: str, client_nonce: str, challenge: str
) -> dict[str, Any]:
    if not valid_challenge(client_nonce):
        raise ValueError("Client nonce must be 32 bytes of lowercase hex")
    if not valid_challenge(challenge):
        raise ValueError("Authentication challenge must be 32 bytes of lowercase hex")
    unsigned = {
        "version": PROTOCOL_VERSION,
        "type": SERVER_HELLO_TYPE,
        "client_nonce": client_nonce,
        "challenge": challenge,
    }
    return {
        **unsigned,
        "server_proof": authentication_proof(token, "server_hello", unsigned),
    }


def authenticated_response(
    token: str,
    client_nonce: str,
    challenge: str,
    response: dict[str, Any],
) -> dict[str, Any]:
    unsigned = {
        **response,
        "client_nonce": client_nonce,
        "challenge": challenge,
    }
    return {
        **unsigned,
        "server_proof": authentication_proof(token, "server_response", unsigned),
    }

def success(request_id: str, result: Any) -> dict[str, Any]:
    return {
        "version": PROTOCOL_VERSION,
        "id": request_id,
        "ok": True,
        "result": result,
    }


def failure(
    request_id: str,
    code: str,
    message: str,
    *,
    retryable: bool = False,
) -> dict[str, Any]:
    return {
        "version": PROTOCOL_VERSION,
        "id": request_id,
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "retryable": retryable,
        },
    }

