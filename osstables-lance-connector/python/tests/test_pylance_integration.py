"""Integration test: real pylance data I/O through OssTablesNamespace.

Exercises the full control-plane path without a real OssTable gateway:

    lance.write_dataset(namespace_client=ns, ...)
      -> pylance Rust PyLanceNamespace trampoline
      -> OssTablesNamespace.declare_table / describe_table  (dict request)
      -> SigV4-signed HTTP request
      -> mock gateway (verifies the signature from raw wire data)
      -> returns a local filesystem location
      -> pylance writes/reads Lance data at that location

This is the closest we can get to end-to-end until the OssTable gateway is
reachable: everything except the real server is real, including pylance's
Rust->Python callback and the signing path.

Requires pylance (``pip install pylance``); skipped if unavailable.
"""

import json
import shutil
import tempfile

import pytest

lance = pytest.importorskip("lance")
pa = pytest.importorskip("pyarrow")

from lance_namespace import connect  # noqa: E402

import osstables_lance_connector  # noqa: F401,E402  (registers the "osstables" alias)

from test_namespace_contract import (  # noqa: E402
    TEST_AK,
    TEST_REGION,
    TEST_SERVICE,
    TEST_SK,
    MockGateway,
)


class LocalBackedGateway(MockGateway):
    """Mock gateway whose table locations point at a local temp directory."""

    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="osstable-ns-it-")
        self.declared = {}
        super().__init__()
        self._install_local_routing()

    def _install_local_routing(self):
        gateway = self

        def _route(handler, method, body):
            path = handler.path.split("?")[0]
            parts = path.split("/")
            # /lance/v1/table/{id}/{action}
            if len(parts) >= 6 and parts[3] == "table":
                from urllib.parse import unquote

                table_id = unquote(parts[4])
                action = parts[5]
                location = f"{gateway.root}/{table_id.replace('$', '_')}.lance"
                if action == "declare":
                    gateway.declared[table_id] = location
                    handler._respond(200, {"location": location})
                    return
                if action == "describe":
                    if table_id not in gateway.declared:
                        handler._respond(404, {"code": 4, "error": "table not found"})
                        return
                    handler._respond(200, {"location": location})
                    return
            handler._respond(404, {"code": 4, "error": f"no route: {path}"})

        self.server.RequestHandlerClass._route = _route

    def stop(self):
        super().stop()
        shutil.rmtree(self.root, ignore_errors=True)


@pytest.fixture()
def gateway():
    gw = LocalBackedGateway()
    yield gw
    errors = list(gw.verification_errors)
    gw.stop()
    assert errors == [], "\n".join(errors)


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


TABLE_ID = ["it_db", "it_table"]


def test_pylance_write_append_read(namespace, gateway):
    data = pa.table({"id": [1, 2, 3], "text": ["a", "b", "c"]})
    ds = lance.write_dataset(
        data, namespace_client=namespace, table_id=TABLE_ID, mode="create"
    )
    assert ds.count_rows() == 3

    ds = lance.write_dataset(
        pa.table({"id": [4, 5], "text": ["d", "e"]}),
        namespace_client=namespace,
        table_id=TABLE_ID,
        mode="append",
    )
    assert ds.count_rows() == 5

    ds = lance.dataset(namespace_client=namespace, table_id=TABLE_ID)
    table = ds.to_table()
    assert table.num_rows == 5
    assert sorted(table.column("id").to_pylist()) == [1, 2, 3, 4, 5]

    # the trampoline really went through our signed HTTP client
    paths = [r["path"] for r in gateway.requests]
    assert any("/table/it_db%24it_table/declare" in p for p in paths)
    assert any("/table/it_db%24it_table/describe" in p for p in paths)
    for request in gateway.requests:
        assert "AWS4-HMAC-SHA256" in request["headers"]["Authorization"]


def test_pylance_open_missing_table_maps_to_not_found(namespace):
    with pytest.raises(Exception) as excinfo:
        lance.dataset(namespace_client=namespace, table_id=["it_db", "nope"])
    assert "not found" in str(excinfo.value).lower()


def test_trampoline_receives_dict_request(namespace, gateway):
    """pylance passes a dict-like request object, not a pydantic model."""
    lance.write_dataset(
        pa.table({"id": [1]}),
        namespace_client=namespace,
        table_id=["it_db", "dict_probe"],
        mode="create",
    )
    declare = [r for r in gateway.requests if "declare" in r["path"]][-1]
    body = json.loads(declare["body"])
    assert body["id"] == ["it_db", "dict_probe"]
