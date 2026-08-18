"""SigV4 unit tests.

Algorithm correctness is pinned against the AWS documented SigV4 example
(GET https://iam.amazonaws.com/?Action=ListUsers&Version=2010-05-08), and the
high-level signer is cross-checked against an independent re-implementation
written from scratch in this file.
"""

import hashlib
import hmac
from datetime import datetime, timezone

import pytest

from osstables_lance_connector.sigv4 import (
    Credentials,
    SigV4Signer,
    canonical_request,
    canonical_query_string,
    canonical_uri,
    host_header_from_url,
    materialize_payload,
    resolve_credentials,
    sha256_hex,
    signing_key,
    string_to_sign,
)

# AWS documented example vector
AWS_AK = "AKIDEXAMPLE"
AWS_SK = "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY"
AWS_REGION = "us-east-1"
AWS_SERVICE = "iam"
AWS_DATE = "20150830T123600Z"
AWS_URL = "https://iam.amazonaws.com/?Action=ListUsers&Version=2010-05-08"
AWS_HEADERS = {
    "host": "iam.amazonaws.com",
    "content-type": "application/x-www-form-urlencoded; charset=utf-8",
    "x-amz-date": AWS_DATE,
}
EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

EXPECTED_CANONICAL_REQUEST = (
    "GET\n"
    "/\n"
    "Action=ListUsers&Version=2010-05-08\n"
    "content-type:application/x-www-form-urlencoded; charset=utf-8\n"
    "host:iam.amazonaws.com\n"
    "x-amz-date:20150830T123600Z\n"
    "\n"
    "content-type;host;x-amz-date\n"
    + EMPTY_SHA256
)
EXPECTED_CREQ_HASH = "f536975d06c0309214f805bb90ccff089219ecd68b2577efef23edd43b7e1a59"
EXPECTED_SIGNING_KEY_HEX = (
    "c4afb1cc5771d871763a393e44b703571b55cc28424d1a5e86da6ed3c154a4b9"
)
EXPECTED_SIGNATURE = "5d672d79c15b13162d9279b0855cfba6789a8edb4c82c400e06b5924a6f2b5d7"


class TestAwsKnownVector:
    def test_canonical_request(self):
        creq, signed_headers = canonical_request(
            "GET", AWS_URL, AWS_HEADERS, EMPTY_SHA256
        )
        assert creq == EXPECTED_CANONICAL_REQUEST
        assert signed_headers == "content-type;host;x-amz-date"
        assert sha256_hex(creq.encode("utf-8")) == EXPECTED_CREQ_HASH

    def test_string_to_sign(self):
        creq, _ = canonical_request("GET", AWS_URL, AWS_HEADERS, EMPTY_SHA256)
        scope = f"20150830/{AWS_REGION}/{AWS_SERVICE}/aws4_request"
        sts = string_to_sign(AWS_DATE, scope, creq)
        assert sts == (
            "AWS4-HMAC-SHA256\n"
            f"{AWS_DATE}\n"
            f"{scope}\n"
            f"{EXPECTED_CREQ_HASH}"
        )

    def test_signing_key(self):
        key = signing_key(AWS_SK, "20150830", AWS_REGION, AWS_SERVICE)
        assert key.hex() == EXPECTED_SIGNING_KEY_HEX

    def test_full_signature(self):
        creq, _ = canonical_request("GET", AWS_URL, AWS_HEADERS, EMPTY_SHA256)
        scope = f"20150830/{AWS_REGION}/{AWS_SERVICE}/aws4_request"
        sts = string_to_sign(AWS_DATE, scope, creq)
        key = signing_key(AWS_SK, "20150830", AWS_REGION, AWS_SERVICE)
        signature = hmac.new(key, sts.encode("utf-8"), hashlib.sha256).hexdigest()
        assert signature == EXPECTED_SIGNATURE


def _independent_signature(
    method, url, signed_header_values, payload, amz_date, region, service, sk
):
    """SigV4 re-implemented from scratch for cross-checking the signer.

    Deliberately avoids the functions in osstables_lance_connector.sigv4.
    """
    from urllib.parse import parse_qsl, quote, urlsplit

    parts = urlsplit(url)
    path = parts.path or "/"
    segments = [quote(seg, safe="-._~") for seg in path.split("/")]
    c_uri = "/".join(segments)
    pairs = sorted(
        (quote(k, safe="-._~"), quote(v, safe="-._~"))
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
    )
    c_query = "&".join(f"{k}={v}" for k, v in pairs)
    items = sorted((k.lower(), " ".join(v.split())) for k, v in signed_header_values.items())
    c_headers = "".join(f"{k}:{v}\n" for k, v in items)
    signed = ";".join(k for k, _ in items)
    payload_hash = hashlib.sha256(payload).hexdigest()
    creq = "\n".join([method, c_uri, c_query, c_headers, signed, payload_hash])
    datestamp = amz_date[:8]
    scope = f"{datestamp}/{region}/{service}/aws4_request"
    sts = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            scope,
            hashlib.sha256(creq.encode()).hexdigest(),
        ]
    )
    key = b"AWS4" + sk.encode()
    for msg in (datestamp, region, service, "aws4_request"):
        key = hmac.new(key, msg.encode(), hashlib.sha256).digest()
    return hmac.new(key, sts.encode(), hashlib.sha256).hexdigest()


class TestSigner:
    REGION = "cn-hangzhou"
    SERVICE = "osstables"
    URL = (
        "https://my-bucket.cn-example-internal.oss-tables.aliyuncs.com"
        "/lance/v1/table/my_db%24my_table/describe?delimiter=%24"
    )
    NOW = datetime(2026, 7, 28, 1, 2, 3, tzinfo=timezone.utc)

    def _signer(self, token=None):
        return SigV4Signer(
            region=self.REGION,
            service=self.SERVICE,
            credentials=Credentials("test-ak", "test-sk", token),
        )

    def test_sign_headers_present(self):
        headers = {"Content-Type": "application/json"}
        result = self._signer().sign(
            "POST", self.URL, headers, b'{"id":["my_db","my_table"]}', now=self.NOW
        )
        assert result["x-amz-date"] == "20260728T010203Z"
        assert result["x-amz-content-sha256"] == sha256_hex(
            b'{"id":["my_db","my_table"]}'
        )
        assert result["Authorization"].startswith(
            "AWS4-HMAC-SHA256 Credential=test-ak/20260728/cn-hangzhou/osstables/aws4_request, "
            "SignedHeaders=content-type;host;x-amz-content-sha256;x-amz-date, "
            "Signature="
        )
        assert "x-amz-security-token" not in result

    def test_sign_matches_independent_implementation(self):
        payload = b'{"id":["my_db","my_table"]}'
        headers = {"Content-Type": "application/json"}
        result = self._signer().sign("POST", self.URL, headers, payload, now=self.NOW)

        # Reconstruct with only wire-visible information
        signed_header_values = {
            "host": "my-bucket.cn-example-internal.oss-tables.aliyuncs.com",
            "content-type": "application/json",
            "x-amz-date": result["x-amz-date"],
            "x-amz-content-sha256": result["x-amz-content-sha256"],
        }
        # Note: the signer double-encodes the canonical URI, so the independent
        # implementation encodes the on-wire path (%24 -> %2524) once more.
        expected = _independent_signature(
            "POST",
            self.URL,
            signed_header_values,
            payload,
            result["x-amz-date"],
            self.REGION,
            self.SERVICE,
            "test-sk",
        )
        assert result["Authorization"].endswith(f"Signature={expected}")

    def test_session_token_signed(self):
        result = self._signer(token="sts-token").sign(
            "POST", self.URL, {"Content-Type": "application/json"}, b"{}", now=self.NOW
        )
        assert result["x-amz-security-token"] == "sts-token"
        assert "x-amz-security-token" in result["Authorization"]

    def test_binary_payload_hash(self):
        arrow_bytes = b"ARROW1\x00\x00" + bytes(range(256))
        result = self._signer().sign(
            "POST",
            self.URL,
            {"Content-Type": "application/vnd.apache.arrow.stream"},
            arrow_bytes,
            now=self.NOW,
        )
        assert result["x-amz-content-sha256"] == hashlib.sha256(arrow_bytes).hexdigest()


class TestCanonicalization:
    def test_host_three_level_domain(self):
        url = "https://my-bucket.cn-example-internal.oss-tables.aliyuncs.com/lance"
        assert (
            host_header_from_url(url)
            == "my-bucket.cn-example-internal.oss-tables.aliyuncs.com"
        )

    def test_host_default_port_omitted(self):
        assert host_header_from_url("https://example.com:443/x") == "example.com"
        assert host_header_from_url("http://example.com:80/x") == "example.com"

    def test_host_custom_port_kept(self):
        assert host_header_from_url("http://127.0.0.1:8080/x") == "127.0.0.1:8080"

    def test_canonical_uri_double_encode(self):
        assert (
            canonical_uri("/lance/v1/table/my_db%24my_table/describe")
            == "/lance/v1/table/my_db%2524my_table/describe"
        )

    def test_canonical_uri_single_encode(self):
        assert (
            canonical_uri(
                "/lance/v1/table/my_db%24my_table/describe", double_uri_encode=False
            )
            == "/lance/v1/table/my_db%24my_table/describe"
        )

    def test_canonical_uri_empty(self):
        assert canonical_uri("") == "/"

    def test_canonical_query_sorted_and_encoded(self):
        assert (
            canonical_query_string("b=2&a=1&a=0&c=a b")
            == "a=0&a=1&b=2&c=a%20b"
        )


class TestMaterializePayload:
    def test_json_dict(self):
        headers = {"Content-Type": "application/json"}
        body = {"id": ["db", "t1"], "version": None}
        import json as _json

        assert materialize_payload(headers, body) == _json.dumps(body).encode("utf-8")

    def test_no_content_type_defaults_to_json(self):
        assert materialize_payload({}, {"a": 1}) == b'{"a": 1}'

    def test_binary_body(self):
        headers = {"Content-Type": "application/vnd.apache.arrow.stream"}
        assert materialize_payload(headers, b"\x00\x01") == b"\x00\x01"

    def test_none_body(self):
        assert materialize_payload({}, None) == b""

    def test_preserialized_json_rejected(self):
        with pytest.raises(ValueError):
            materialize_payload({"Content-Type": "application/json"}, '{"a": 1}')

    def test_unsupported_body_rejected(self):
        with pytest.raises(ValueError):
            materialize_payload({"Content-Type": "text/plain"}, {"a": 1})


class TestResolveCredentials:
    ENV_KEYS = [
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "ALIBABA_CLOUD_ACCESS_KEY_ID",
        "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
        "ALIBABA_CLOUD_SECURITY_TOKEN",
    ]

    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch):
        for key in self.ENV_KEYS:
            monkeypatch.delenv(key, raising=False)

    def test_explicit(self):
        creds = resolve_credentials(
            {
                "osstables.access_key_id": "ak",
                "osstables.secret_access_key": "sk",
                "osstables.session_token": "t",
            }
        )
        assert creds == Credentials("ak", "sk", "t")

    def test_explicit_partial_rejected(self):
        with pytest.raises(ValueError):
            resolve_credentials({"osstables.access_key_id": "ak"})

    def test_aws_env(self, monkeypatch):
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "env-ak")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "env-sk")
        assert resolve_credentials({}) == Credentials("env-ak", "env-sk", None)

    def test_alibaba_env(self, monkeypatch):
        monkeypatch.setenv("ALIBABA_CLOUD_ACCESS_KEY_ID", "ali-ak")
        monkeypatch.setenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "ali-sk")
        monkeypatch.setenv("ALIBABA_CLOUD_SECURITY_TOKEN", "ali-token")
        assert resolve_credentials({}) == Credentials("ali-ak", "ali-sk", "ali-token")

    def test_alibaba_takes_precedence_over_aws(self, monkeypatch):
        monkeypatch.setenv("ALIBABA_CLOUD_ACCESS_KEY_ID", "ali-ak")
        monkeypatch.setenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "ali-sk")
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "aws-ak")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-sk")
        assert resolve_credentials({}) == Credentials("ali-ak", "ali-sk", None)

    def test_missing(self):
        with pytest.raises(ValueError):
            resolve_credentials({})
