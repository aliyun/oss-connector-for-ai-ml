"""AWS Signature Version 4 signing for the OssTable Lance REST Namespace.

Implements the SigV4 algorithm (canonical request, string-to-sign, derived
signing key) and a `SigV4ApiClient` that injects the signature into every
request made by the generated `lance_namespace_urllib3_client`.

The signature is computed at the `ApiClient.call_api` boundary where the
request method / URL / headers / body are fully materialized, so the payload
hash is guaranteed to match the bytes actually sent on the wire (including
Arrow IPC binary bodies for `create_table`).
"""

import hashlib
import hmac
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, quote, urlsplit

from lance_namespace_urllib3_client.api_client import ApiClient

__all__ = [
    "Credentials",
    "resolve_credentials",
    "SigV4Signer",
    "SigV4ApiClient",
    "materialize_payload",
    "host_header_from_url",
    "sha256_hex",
    "PROPERTY_PREFIX",
    "PROP_REGION",
    "PROP_SERVICE",
    "PROP_ACCESS_KEY_ID",
    "PROP_SECRET_ACCESS_KEY",
    "PROP_SESSION_TOKEN",
    "PROP_DOUBLE_URI_ENCODE",
]

# Every property this implementation reads is namespaced with ``osstables.`` so it
# can never be confused with the data-plane OSS options (``storage_options`` /
# ``storage.`` prefix).
PROPERTY_PREFIX = "osstables."
PROP_REGION = PROPERTY_PREFIX + "region"
PROP_SERVICE = PROPERTY_PREFIX + "service"
PROP_ACCESS_KEY_ID = PROPERTY_PREFIX + "access_key_id"
PROP_SECRET_ACCESS_KEY = PROPERTY_PREFIX + "secret_access_key"
PROP_SESSION_TOKEN = PROPERTY_PREFIX + "session_token"
PROP_DOUBLE_URI_ENCODE = PROPERTY_PREFIX + "double_uri_encode"

_ALGORITHM = "AWS4-HMAC-SHA256"
_UNRESERVED = "-._~"
_DEFAULT_PORTS = {"http": 80, "https": 443}


@dataclass(frozen=True)
class Credentials:
    access_key_id: str
    secret_access_key: str
    session_token: Optional[str] = None


def resolve_credentials(properties: Dict[str, str]) -> Credentials:
    """Resolve credentials from explicit properties, then environment variables.

    Order:
    1. Explicit ``osstables.access_key_id`` / ``osstables.secret_access_key`` /
       ``osstables.session_token`` properties.
    2. ``ALIBABA_CLOUD_ACCESS_KEY_ID`` / ``ALIBABA_CLOUD_ACCESS_KEY_SECRET`` /
       ``ALIBABA_CLOUD_SECURITY_TOKEN``.
    3. ``AWS_ACCESS_KEY_ID`` / ``AWS_SECRET_ACCESS_KEY`` / ``AWS_SESSION_TOKEN``.
    """
    ak = properties.get(PROP_ACCESS_KEY_ID)
    sk = properties.get(PROP_SECRET_ACCESS_KEY)
    token = properties.get(PROP_SESSION_TOKEN)
    if ak and sk:
        return Credentials(ak, sk, token or None)
    if ak or sk:
        raise ValueError(
            f"Both {PROP_ACCESS_KEY_ID} and {PROP_SECRET_ACCESS_KEY} "
            "must be provided together"
        )

    for ak_env, sk_env, token_env in (
        (
            "ALIBABA_CLOUD_ACCESS_KEY_ID",
            "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
            "ALIBABA_CLOUD_SECURITY_TOKEN",
        ),
        ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"),
    ):
        env_ak = os.environ.get(ak_env)
        env_sk = os.environ.get(sk_env)
        if env_ak and env_sk:
            return Credentials(env_ak, env_sk, os.environ.get(token_env) or None)

    raise ValueError(
        f"No credentials found: set {PROP_ACCESS_KEY_ID}/"
        f"{PROP_SECRET_ACCESS_KEY} properties, "
        "or ALIBABA_CLOUD_ACCESS_KEY_ID/ALIBABA_CLOUD_ACCESS_KEY_SECRET, "
        "or AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY "
        "environment variables"
    )


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hmac_sha256(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _uri_encode(value: str, encode_slash: bool = True) -> str:
    safe = _UNRESERVED if encode_slash else _UNRESERVED + "/"
    return quote(value, safe=safe)


def host_header_from_url(url: str) -> str:
    """Compute the Host header exactly as urllib3/http.client will send it.

    The port is omitted when it is the default for the scheme.
    """
    parts = urlsplit(url)
    host = parts.hostname or ""
    port = parts.port
    if port is not None and port != _DEFAULT_PORTS.get(parts.scheme.lower()):
        return f"{host}:{port}"
    return host


def canonical_uri(path: str, double_uri_encode: bool = True) -> str:
    """Build the canonical URI from the on-wire (already percent-encoded) path.

    With ``double_uri_encode`` (the default, matching the aws-sigv4 crate used
    by Lance PR #7099 for non-S3 services), each on-wire path segment is
    percent-encoded once more.
    """
    if not path:
        return "/"
    if not double_uri_encode:
        return path
    segments = path.split("/")
    return "/".join(_uri_encode(seg) for seg in segments)


def canonical_query_string(query: str) -> str:
    if not query:
        return ""
    pairs = parse_qsl(query, keep_blank_values=True)
    encoded = sorted(
        (_uri_encode(str(k)), _uri_encode(str(v))) for k, v in pairs
    )
    return "&".join(f"{k}={v}" for k, v in encoded)


def canonical_headers(headers: Dict[str, str]) -> Tuple[str, str]:
    """Return (canonical_headers, signed_headers) for the given headers."""
    normalized = sorted(
        (name.lower(), " ".join(str(value).split()))
        for name, value in headers.items()
    )
    canonical = "".join(f"{name}:{value}\n" for name, value in normalized)
    signed = ";".join(name for name, _ in normalized)
    return canonical, signed


def canonical_request(
    method: str,
    url: str,
    headers_to_sign: Dict[str, str],
    payload_hash: str,
    double_uri_encode: bool = True,
) -> Tuple[str, str]:
    """Build the SigV4 canonical request. Returns (canonical_request, signed_headers)."""
    parts = urlsplit(url)
    c_headers, signed_headers = canonical_headers(headers_to_sign)
    creq = "\n".join(
        [
            method.upper(),
            canonical_uri(parts.path, double_uri_encode),
            canonical_query_string(parts.query),
            c_headers,
            signed_headers,
            payload_hash,
        ]
    )
    return creq, signed_headers


def string_to_sign(amz_date: str, scope: str, creq: str) -> str:
    return "\n".join(
        [_ALGORITHM, amz_date, scope, sha256_hex(creq.encode("utf-8"))]
    )


def signing_key(secret_access_key: str, datestamp: str, region: str, service: str) -> bytes:
    k_date = _hmac_sha256(("AWS4" + secret_access_key).encode("utf-8"), datestamp)
    k_region = _hmac_sha256(k_date, region)
    k_service = _hmac_sha256(k_region, service)
    return _hmac_sha256(k_service, "aws4_request")


class SigV4Signer:
    """Computes SigV4 signature headers for HTTP requests."""

    def __init__(
        self,
        region: str,
        service: str,
        credentials: Credentials,
        double_uri_encode: bool = True,
    ):
        self.region = region
        self.service = service
        self.credentials = credentials
        self.double_uri_encode = double_uri_encode

    def sign(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        payload: bytes,
        now: Optional[datetime] = None,
    ) -> Dict[str, str]:
        """Compute signature headers for a fully materialized request.

        Returns the headers to add: ``x-amz-date``, ``x-amz-content-sha256``,
        optional ``x-amz-security-token``, and ``Authorization``.
        """
        if now is None:
            now = datetime.now(timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        datestamp = amz_date[:8]
        payload_hash = sha256_hex(payload)

        new_headers: Dict[str, str] = {
            "x-amz-date": amz_date,
            "x-amz-content-sha256": payload_hash,
        }
        if self.credentials.session_token:
            new_headers["x-amz-security-token"] = self.credentials.session_token

        headers_to_sign = {"host": host_header_from_url(url)}
        content_type = _get_header(headers, "content-type")
        if content_type is not None:
            headers_to_sign["content-type"] = content_type
        headers_to_sign.update(new_headers)

        creq, signed_headers = canonical_request(
            method, url, headers_to_sign, payload_hash, self.double_uri_encode
        )
        scope = f"{datestamp}/{self.region}/{self.service}/aws4_request"
        sts = string_to_sign(amz_date, scope, creq)
        key = signing_key(
            self.credentials.secret_access_key, datestamp, self.region, self.service
        )
        signature = hmac.new(key, sts.encode("utf-8"), hashlib.sha256).hexdigest()

        new_headers["Authorization"] = (
            f"{_ALGORITHM} "
            f"Credential={self.credentials.access_key_id}/{scope}, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )
        return new_headers


def _get_header(headers: Dict[str, str], name: str) -> Optional[str]:
    for key, value in headers.items():
        if key.lower() == name:
            return value
    return None


def materialize_payload(headers: Dict[str, str], body) -> bytes:
    """Materialize the request body into the exact bytes urllib3 will send.

    Mirrors the serialization logic in
    ``lance_namespace_urllib3_client.rest.RESTClientObject.request``:
    JSON content types are serialized with ``json.dumps``; str/bytes bodies
    (e.g. Arrow IPC) are sent as-is.
    """
    if body is None:
        return b""
    content_type = _get_header(headers, "content-type")
    if not content_type or re.search("json", content_type, re.IGNORECASE):
        if isinstance(body, (str, bytes)):
            raise ValueError(
                "Refusing to sign a pre-serialized body with JSON content type: "
                "the generated client would serialize it again and the "
                "signature would not match the wire bytes"
            )
        return json.dumps(body).encode("utf-8")
    if isinstance(body, bytes):
        return body
    if isinstance(body, str):
        return body.encode("utf-8")
    raise ValueError(
        f"Cannot materialize request body of type {type(body).__name__} "
        f"with content type {content_type!r} for SigV4 signing"
    )


class SigV4ApiClient(ApiClient):
    """Generated ApiClient subclass that SigV4-signs every request.

    ``call_api`` is the single choke point where method / url / headers / body
    are all finalized, for every operation of the generated client.
    """

    def __init__(self, configuration, signer: SigV4Signer):
        super().__init__(configuration=configuration)
        self._signer = signer

    def call_api(
        self,
        method,
        url,
        header_params=None,
        body=None,
        post_params=None,
        _request_timeout=None,
    ):
        if post_params:
            raise ValueError(
                "SigV4 signing does not support form/multipart request bodies"
            )
        header_params = dict(header_params or {})
        payload = materialize_payload(header_params, body)
        header_params.update(self._signer.sign(method, url, header_params, payload))
        return super().call_api(
            method,
            url,
            header_params=header_params,
            body=body,
            post_params=post_params,
            _request_timeout=_request_timeout,
        )
