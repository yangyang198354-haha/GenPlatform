"""
Shared Volcengine HMAC-SHA256 request signing utility.
Used by both video_generator and image_generator apps.
"""
import hashlib
import hmac
import time

JIMENG_API_BASE = "https://visual.volcengineapi.com"
JIMENG_SERVICE = "visual"
JIMENG_REGION = "cn-north-1"
JIMENG_VERSION = "2024-05-01"


def sign_request(access_key: str, secret_key: str, method: str, path: str, params: dict, body: str) -> dict:
    """
    Generate Volcengine HMAC-SHA256 signature headers.

    Returns a dict of HTTP headers including Authorization, X-Date, Content-Type, Host.
    Reference: https://www.volcengine.com/docs/6791/1389702
    """
    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    date = timestamp[:8]

    canonical_query = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    host = JIMENG_API_BASE.split("://")[1]
    canonical_headers = f"content-type:application/json\nhost:{host}\nx-date:{timestamp}\n"
    signed_headers = "content-type;host;x-date"

    body_hash = hashlib.sha256(body.encode()).hexdigest()
    canonical_request = "\n".join([
        method,
        path,
        canonical_query,
        canonical_headers,
        signed_headers,
        body_hash,
    ])

    credential_scope = f"{date}/{JIMENG_REGION}/{JIMENG_SERVICE}/request"
    string_to_sign = "\n".join([
        "HMAC-SHA256",
        timestamp,
        credential_scope,
        hashlib.sha256(canonical_request.encode()).hexdigest(),
    ])

    def _hmac(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    signing_key = _hmac(
        _hmac(_hmac(_hmac(secret_key.encode(), date), JIMENG_REGION), JIMENG_SERVICE),
        "request",
    )
    signature = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()

    return {
        "Content-Type": "application/json",
        "Host": host,
        "X-Date": timestamp,
        "Authorization": (
            f"HMAC-SHA256 Credential={access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        ),
    }
