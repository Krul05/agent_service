from __future__ import annotations

import hmac
import hashlib


def verify_github_signature(secret: str, body: bytes, signature_256: str | None) -> bool:

    if not secret or not signature_256:
        return False
    if not signature_256.startswith("sha256="):
        return False

    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    got = signature_256.split("=", 1)[1]
    return hmac.compare_digest(expected, got)
