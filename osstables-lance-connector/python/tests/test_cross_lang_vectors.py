"""Cross-language SigV4 conformance (Python side).

Guards the shared sigv4_vectors.json — the same file the Java CrossLangVectorTest
asserts against — so the reference implementation and the file cannot drift.
Regenerate with: python scripts/generate_vectors.py
"""

import json
import os
from datetime import datetime, timezone

import pytest

from osstables_lance_connector.sigv4 import (
    Credentials,
    SigV4Signer,
    canonical_query_string,
    canonical_uri,
    host_header_from_url,
    signing_key,
)

VECTORS_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    "java",
    "src",
    "test",
    "resources",
    "sigv4_vectors.json",
)

with open(VECTORS_PATH) as f:
    VECTORS = json.load(f)


@pytest.mark.parametrize("case", VECTORS["canonical_uri"])
def test_canonical_uri(case):
    assert (
        canonical_uri(case["raw_path"], case["double_uri_encode"]) == case["expected"]
    )


@pytest.mark.parametrize("case", VECTORS["canonical_query"])
def test_canonical_query(case):
    assert canonical_query_string(case["raw_query"]) == case["expected"]


@pytest.mark.parametrize("case", VECTORS["host_header"])
def test_host_header(case):
    assert host_header_from_url(case["url"]) == case["expected"]


@pytest.mark.parametrize("case", VECTORS["signing_key"])
def test_signing_key(case):
    key = signing_key(
        case["secret_access_key"], case["datestamp"], case["region"], case["service"]
    )
    assert key.hex() == case["expected_hex"]


@pytest.mark.parametrize("case", VECTORS["signature"], ids=lambda c: c["name"])
def test_signature(case):
    now = datetime.strptime(case["amz_date"], "%Y%m%dT%H%M%SZ").replace(
        tzinfo=timezone.utc
    )
    signer = SigV4Signer(
        region=case["region"],
        service=case["service"],
        credentials=Credentials(
            case["access_key_id"], case["secret_access_key"], case["session_token"]
        ),
        double_uri_encode=case["double_uri_encode"],
    )
    headers = {} if case["content_type"] is None else {"Content-Type": case["content_type"]}
    payload = bytes.fromhex(case["payload_hex"])
    result = signer.sign(case["method"], case["url"], headers, payload, now=now)
    assert result["Authorization"] == case["expected_authorization"]
