"""Contract tests: run OssTablesNamespace against a local mock HTTP server that
verifies every request's SigV4 signature from the raw wire data.

The server-side check recomputes:
1. sha256(received body bytes) == x-amz-content-sha256 header
   (the critical byte-consistency guarantee, fully independent of the signer)
2. the signature from the on-wire method/path/query/headers using the
   documented SigV4 algorithm
"""

import hashlib
import hmac
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from lance_namespace import (
    CreateNamespaceRequest,
    CreateTableRequest,
    DeclareTableRequest,
    DescribeTableRequest,
    TableNotFoundError,
    UnauthenticatedError,
    connect,
)

import osstables_lance_connector  # noqa: F401  (registers the "osstables" alias)

TEST_AK = "contract-test-ak"
TEST_SK = "contract-test-sk"
TEST_REGION = "cn-hangzhou"
TEST_SERVICE = "osstables"

_AUTH_RE = re.compile(
    r"AWS4-HMAC-SHA256 "
    r"Credential=(?P<ak>[^/]+)/(?P<date>\d{8})/(?P<region>[^/]+)/(?P<service>[^/]+)/aws4_request, "
    r"SignedHeaders=(?P<signed>[^,]+), "
    r"Signature=(?P<signature>[0-9a-f]{64})"
)


def _sigv4_verify(method, raw_path, headers, body, secret_key):
    """Recompute the SigV4 signature from raw wire data. Returns error or None."""
    auth = headers.get("Authorization")
    if not auth:
        return "missing Authorization header"
    match = _AUTH_RE.match(auth)
    if not match:
        return f"malformed Authorization header: {auth}"
    if match["ak"] != TEST_AK:
        return f"unexpected access key: {match['ak']}"
    if match["region"] != TEST_REGION or match["service"] != TEST_SERVICE:
        return f"unexpected scope: {auth}"

    payload_hash = headers.get("x-amz-content-sha256")
    if payload_hash != hashlib.sha256(body).hexdigest():
        return (
            f"payload hash mismatch: header={payload_hash} "
            f"actual={hashlib.sha256(body).hexdigest()}"
        )

    from urllib.parse import parse_qsl, quote

    path, _, query = raw_path.partition("?")
    # canonical URI: double-encode the on-wire path segments (non-S3 SigV4)
    c_uri = "/".join(quote(seg, safe="-._~") for seg in path.split("/"))
    pairs = sorted(
        (quote(k, safe="-._~"), quote(v, safe="-._~"))
        for k, v in parse_qsl(query, keep_blank_values=True)
    )
    c_query = "&".join(f"{k}={v}" for k, v in pairs)

    signed_names = match["signed"].split(";")
    items = []
    for name in signed_names:
        value = headers.get(name)
        if value is None:
            return f"signed header {name} not present in request"
        items.append((name.lower(), " ".join(value.split())))
    items.sort()
    c_headers = "".join(f"{k}:{v}\n" for k, v in items)

    creq = "\n".join(
        [method, c_uri, c_query, c_headers, match["signed"], payload_hash]
    )
    amz_date = headers.get("x-amz-date")
    if not amz_date or amz_date[:8] != match["date"]:
        return f"x-amz-date {amz_date} does not match credential date {match['date']}"
    scope = f"{match['date']}/{TEST_REGION}/{TEST_SERVICE}/aws4_request"
    sts = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            scope,
            hashlib.sha256(creq.encode()).hexdigest(),
        ]
    )
    key = b"AWS4" + secret_key.encode()
    for msg in (match["date"], TEST_REGION, TEST_SERVICE, "aws4_request"):
        key = hmac.new(key, msg.encode(), hashlib.sha256).digest()
    expected = hmac.new(key, sts.encode(), hashlib.sha256).hexdigest()
    if expected != match["signature"]:
        return (
            f"signature mismatch: expected={expected} got={match['signature']}\n"
            f"canonical request:\n{creq}"
        )
    return None


class MockGateway:
    def __init__(self):
        self.requests = []
        self.verification_errors = []
        gateway = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self._handle("GET")

            def do_POST(self):
                self._handle("POST")

            def do_DELETE(self):
                self._handle("DELETE")

            def _handle(self, method):
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length)
                error = _sigv4_verify(method, self.path, self.headers, body, TEST_SK)
                if error:
                    gateway.verification_errors.append(f"{method} {self.path}: {error}")
                    self._respond(
                        401, {"code": 16, "error": f"signature invalid: {error}"}
                    )
                    return
                gateway.requests.append(
                    {
                        "method": method,
                        "path": self.path,
                        "headers": dict(self.headers.items()),
                        "body": body,
                    }
                )
                self._route(method, body)

            def _route(self, method, body):
                path = self.path.split("?")[0]
                if path == "/lance/v1/table/my_db%24missing/describe":
                    self._respond(404, {"code": 4, "error": "table not found"})
                elif path.endswith("/describe") and "/table/" in path:
                    self._respond(
                        200,
                        {
                            "location": "oss://bucket/my_db/my_table",
                            "version": 3,
                            "storage_options": {"region": TEST_REGION},
                        },
                    )
                elif path.endswith("/declare"):
                    self._respond(200, {"location": "oss://bucket/my_db/new_table"})
                elif path.endswith("/create") and "/namespace/" in path:
                    self._respond(200, {"properties": {}})
                elif path.endswith("/create") and "/table/" in path:
                    self._respond(
                        200, {"location": "oss://bucket/my_db/created", "version": 1}
                    )
                else:
                    self._respond(404, {"code": 4, "error": f"no route: {path}"})

            def _respond(self, status, payload):
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def uri(self):
        return f"http://127.0.0.1:{self.server.server_port}/lance"

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture()
def gateway():
    gw = MockGateway()
    yield gw
    gw.stop()
    assert gw.verification_errors == [], "\n".join(gw.verification_errors)


@pytest.fixture()
def namespace(gateway):
    return connect(
        "osstables",
        {
            "osstables.uri": gateway.uri,
            "osstables.region": TEST_REGION,
            "osstables.service": TEST_SERVICE,
            "osstables.access_key_id": TEST_AK,
            "osstables.secret_access_key": TEST_SK,
        },
    )


class TestContract:
    def test_connect_by_class_path(self, gateway):
        ns = connect(
            "osstables_lance_connector.OssTablesNamespace",
            {
                "osstables.uri": gateway.uri,
                "osstables.region": TEST_REGION,
                "osstables.access_key_id": TEST_AK,
                "osstables.secret_access_key": TEST_SK,
            },
        )
        assert "OssTablesNamespace" in ns.namespace_id()

    def test_describe_table(self, namespace, gateway):
        response = namespace.describe_table(
            DescribeTableRequest(id=["my_db", "my_table"])
        )
        assert response.location == "oss://bucket/my_db/my_table"
        assert response.version == 3
        request = gateway.requests[-1]
        assert request["path"].startswith("/lance/v1/table/my_db%24my_table/describe")
        assert "delimiter=%24" in request["path"]

    def test_describe_table_with_dict_request(self, namespace, gateway):
        # The pylance Rust trampoline passes a dict-like request
        response = namespace.describe_table({"id": ["my_db", "my_table"], "version": None})
        assert response.location == "oss://bucket/my_db/my_table"

    def test_declare_table(self, namespace, gateway):
        response = namespace.declare_table(
            DeclareTableRequest(id=["my_db", "new_table"])
        )
        assert response.location == "oss://bucket/my_db/new_table"
        assert gateway.requests[-1]["path"].startswith(
            "/lance/v1/table/my_db%24new_table/declare"
        )

    def test_create_namespace(self, namespace, gateway):
        namespace.create_namespace(CreateNamespaceRequest(id=["my_db"]))
        assert gateway.requests[-1]["path"].startswith("/lance/v1/namespace/my_db/create")

    def test_create_table_binary_body(self, namespace, gateway):
        arrow_ipc = b"ARROW1\x00\x00" + bytes(range(256)) * 4
        response = namespace.create_table(
            CreateTableRequest(id=["my_db", "created"], mode="create"), arrow_ipc
        )
        assert response.location == "oss://bucket/my_db/created"
        request = gateway.requests[-1]
        assert request["body"] == arrow_ipc
        assert request["headers"]["Content-Type"] == "application/vnd.apache.arrow.stream"
        assert "mode=create" in request["path"]

    def test_error_mapping_table_not_found(self, namespace):
        with pytest.raises(TableNotFoundError):
            namespace.describe_table(DescribeTableRequest(id=["my_db", "missing"]))

    def test_session_token_header_signed(self, gateway):
        ns = connect(
            "osstables",
            {
                "osstables.uri": gateway.uri,
                "osstables.region": TEST_REGION,
                "osstables.access_key_id": TEST_AK,
                "osstables.secret_access_key": TEST_SK,
                "osstables.session_token": "sts-session-token",
            },
        )
        ns.describe_table(DescribeTableRequest(id=["my_db", "my_table"]))
        request = gateway.requests[-1]
        assert request["headers"]["x-amz-security-token"] == "sts-session-token"
        assert "x-amz-security-token" in request["headers"]["Authorization"]

    def test_bad_secret_rejected_by_gateway(self, gateway):
        ns = connect(
            "osstables",
            {
                "osstables.uri": gateway.uri,
                "osstables.region": TEST_REGION,
                "osstables.access_key_id": TEST_AK,
                "osstables.secret_access_key": "wrong-sk",
            },
        )
        with pytest.raises(UnauthenticatedError):
            ns.describe_table(DescribeTableRequest(id=["my_db", "my_table"]))
        # this failure is expected; do not fail the fixture teardown
        gateway.verification_errors.clear()
