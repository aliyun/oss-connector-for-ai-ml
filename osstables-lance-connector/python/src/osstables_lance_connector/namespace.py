"""OssTable Lance Namespace implementation (SigV4-signed Lance REST client)."""

import json
from contextlib import contextmanager
from typing import List, Optional

from lance_namespace import (
    CreateNamespaceRequest,
    CreateNamespaceResponse,
    CreateTableRequest,
    CreateTableResponse,
    CreateTableVersionRequest,
    CreateTableVersionResponse,
    DeclareTableRequest,
    DeclareTableResponse,
    DeregisterTableRequest,
    DeregisterTableResponse,
    DescribeNamespaceRequest,
    DescribeNamespaceResponse,
    DescribeTableRequest,
    DescribeTableResponse,
    DescribeTableVersionRequest,
    DescribeTableVersionResponse,
    DropNamespaceRequest,
    DropNamespaceResponse,
    DropTableRequest,
    DropTableResponse,
    InternalError,
    InvalidInputError,
    LanceNamespace,
    ListNamespacesRequest,
    ListNamespacesResponse,
    ListTablesRequest,
    ListTablesResponse,
    ListTableVersionsRequest,
    ListTableVersionsResponse,
    NamespaceExistsRequest,
    PermissionDeniedError,
    RenameTableRequest,
    RenameTableResponse,
    ServiceUnavailableError,
    TableExistsRequest,
    ThrottlingError,
    UnauthenticatedError,
    from_error_code,
)
from lance_namespace_urllib3_client import Configuration, NamespaceApi, TableApi
from lance_namespace_urllib3_client.exceptions import ApiException

from .sigv4 import (
    PROP_REGION,
    PROP_SERVICE,
    PROPERTY_PREFIX,
    SigV4ApiClient,
    SigV4Signer,
    resolve_credentials,
)

__all__ = ["OssTablesNamespace"]

PROP_URI = PROPERTY_PREFIX + "uri"
PROP_DELIMITER = PROPERTY_PREFIX + "delimiter"
PROP_VERIFY_SSL = PROPERTY_PREFIX + "verify_ssl"
PROP_DOUBLE_URI_ENCODE = PROPERTY_PREFIX + "double_uri_encode"

_SERVICE = "osstables"


def _parse_boolean_property(properties, key, default):
    if key not in properties:
        return default
    value = str(properties[key]).lower()
    if value == "true":
        return True
    if value == "false":
        return False
    raise ValueError(
        f"Property '{key}' must be 'true' or 'false', got {properties[key]!r}"
    )


_STATUS_ERRORS = {
    400: InvalidInputError,
    401: UnauthenticatedError,
    403: PermissionDeniedError,
    429: ThrottlingError,
    503: ServiceUnavailableError,
}


def _to_model(request, model_cls):
    if isinstance(request, model_cls):
        return request
    if isinstance(request, dict):
        return model_cls.from_dict(dict(request))
    if hasattr(request, "model_dump"):
        return model_cls.from_dict(request.model_dump())
    raise InvalidInputError(
        f"Cannot convert {type(request).__name__} to {model_cls.__name__}"
    )


def _to_namespace_error(exc: ApiException):
    message = None
    code = None
    if exc.body:
        try:
            parsed = json.loads(exc.body)
            code = parsed.get("code")
            message = parsed.get("error") or parsed.get("detail")
        except (ValueError, AttributeError):
            pass
    message = message or f"HTTP {exc.status}: {exc.body or exc.reason}"
    if isinstance(code, int):
        return from_error_code(code, message)
    error_cls = _STATUS_ERRORS.get(exc.status, InternalError)
    return error_cls(message)


@contextmanager
def _translate_errors():
    try:
        yield
    except ApiException as exc:
        raise _to_namespace_error(exc) from exc


class OssTablesNamespace(LanceNamespace):
    """Lance Namespace for OssTable: standard Lance REST protocol + SigV4 auth.

    Properties
    ----------
    All properties are namespaced with ``osstables.`` so they can never be
    confused with the data-plane OSS options (``storage_options``).

    osstables.uri : str (required)
        Catalog endpoint, e.g.
        ``https://{bucket}.{region}-internal.oss-tables.aliyuncs.com/lance``
    osstables.region : str (required)
        SigV4 region, e.g. ``cn-hangzhou``
    osstables.access_key_id / osstables.secret_access_key : str (optional)
        Explicit credentials; falls back to environment variables
        (ALIBABA_CLOUD_* then AWS_*)
    osstables.session_token : str (optional)
        STS session token
    osstables.delimiter : str (optional, default ``$``)
        Object identifier delimiter
    osstables.verify_ssl : str (optional, default ``true``)
        Set ``"false"`` to skip TLS certificate verification

    Examples
    --------
    >>> import lance_namespace
    >>> ns = lance_namespace.connect(
    ...     "osstables_lance_connector.OssTablesNamespace",
    ...     {
    ...         "osstables.uri": "https://bucket.cn-example-internal.oss-tables.aliyuncs.com/lance",
    ...         "osstables.region": "cn-hangzhou",
    ...         "osstables.access_key_id": "ak",
    ...         "osstables.secret_access_key": "sk",
    ...     },
    ... )  # doctest: +SKIP
    """

    def __init__(self, **properties):
        uri = properties.get(PROP_URI)
        if not uri:
            raise ValueError(f"Property '{PROP_URI}' is required")
        region = properties.get(PROP_REGION)
        if not region:
            raise ValueError(f"Property '{PROP_REGION}' is required")
        service = properties.get(PROP_SERVICE, _SERVICE)
        if service != _SERVICE:
            raise ValueError(
                f"Property '{PROP_SERVICE}' must be '{_SERVICE}', got {service!r}"
            )
        double_uri_encode = _parse_boolean_property(
            properties, PROP_DOUBLE_URI_ENCODE, True
        )
        if not double_uri_encode:
            raise ValueError(
                f"Property '{PROP_DOUBLE_URI_ENCODE}' must be true; "
                "OssTables requires double URI encoding"
            )
        self._uri = uri.rstrip("/")
        self._region = region
        self._service = service
        self._delimiter = properties.get(PROP_DELIMITER, "$")
        credentials = resolve_credentials(properties)
        signer = SigV4Signer(
            region=region,
            service=service,
            credentials=credentials,
        )
        configuration = Configuration(host=self._uri)
        verify_ssl = _parse_boolean_property(properties, PROP_VERIFY_SSL, True)
        if not verify_ssl:
            configuration.verify_ssl = False
            import urllib3

            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self._client = SigV4ApiClient(configuration, signer)
        self._namespace_api = NamespaceApi(self._client)
        self._table_api = TableApi(self._client)

    def namespace_id(self) -> str:
        return (
            f'OssTablesNamespace {{ uri: "{self._uri}", '
            f'region: "{self._region}", service: "{self._service}" }}'
        )

    def __repr__(self) -> str:
        return self.namespace_id()

    def _id_string(self, id_parts: Optional[List[str]]) -> str:
        if id_parts is None:
            raise InvalidInputError("Object ID is required")
        if not id_parts:
            return self._delimiter
        return self._delimiter.join(id_parts)

    # Namespace operations

    def create_namespace(
        self, request: CreateNamespaceRequest
    ) -> CreateNamespaceResponse:
        req = _to_model(request, CreateNamespaceRequest)
        with _translate_errors():
            return self._namespace_api.create_namespace(
                id=self._id_string(req.id),
                create_namespace_request=req,
                delimiter=self._delimiter,
            )

    def describe_namespace(
        self, request: DescribeNamespaceRequest
    ) -> DescribeNamespaceResponse:
        req = _to_model(request, DescribeNamespaceRequest)
        with _translate_errors():
            return self._namespace_api.describe_namespace(
                id=self._id_string(req.id),
                describe_namespace_request=req,
                delimiter=self._delimiter,
            )

    def list_namespaces(
        self, request: ListNamespacesRequest
    ) -> ListNamespacesResponse:
        req = _to_model(request, ListNamespacesRequest)
        with _translate_errors():
            return self._namespace_api.list_namespaces(
                id=self._id_string(req.id),
                delimiter=self._delimiter,
                page_token=req.page_token,
                limit=req.limit,
            )

    def drop_namespace(self, request: DropNamespaceRequest) -> DropNamespaceResponse:
        req = _to_model(request, DropNamespaceRequest)
        with _translate_errors():
            return self._namespace_api.drop_namespace(
                id=self._id_string(req.id),
                drop_namespace_request=req,
                delimiter=self._delimiter,
            )

    def namespace_exists(self, request: NamespaceExistsRequest) -> None:
        req = _to_model(request, NamespaceExistsRequest)
        with _translate_errors():
            return self._namespace_api.namespace_exists(
                id=self._id_string(req.id),
                namespace_exists_request=req,
                delimiter=self._delimiter,
            )

    def list_tables(self, request: ListTablesRequest) -> ListTablesResponse:
        req = _to_model(request, ListTablesRequest)
        with _translate_errors():
            return self._namespace_api.list_tables(
                id=self._id_string(req.id),
                delimiter=self._delimiter,
                page_token=req.page_token,
                limit=req.limit,
                include_declared=req.include_declared,
            )

    # Table operations

    def describe_table(self, request: DescribeTableRequest) -> DescribeTableResponse:
        req = _to_model(request, DescribeTableRequest)
        with _translate_errors():
            return self._table_api.describe_table(
                id=self._id_string(req.id),
                describe_table_request=req,
                delimiter=self._delimiter,
                with_table_uri=req.with_table_uri,
                load_detailed_metadata=req.load_detailed_metadata,
                check_declared=req.check_declared,
            )

    def declare_table(self, request: DeclareTableRequest) -> DeclareTableResponse:
        req = _to_model(request, DeclareTableRequest)
        with _translate_errors():
            return self._table_api.declare_table(
                id=self._id_string(req.id),
                declare_table_request=req,
                delimiter=self._delimiter,
            )

    def create_table(
        self, request: CreateTableRequest, request_data: bytes
    ) -> CreateTableResponse:
        req = _to_model(request, CreateTableRequest)
        with _translate_errors():
            return self._table_api.create_table(
                id=self._id_string(req.id),
                body=request_data,
                delimiter=self._delimiter,
                mode=req.mode,
                properties=json.dumps(req.properties) if req.properties else None,
                storage_options=(
                    json.dumps(req.storage_options) if req.storage_options else None
                ),
            )

    def drop_table(self, request: DropTableRequest) -> DropTableResponse:
        req = _to_model(request, DropTableRequest)
        with _translate_errors():
            return self._table_api.drop_table(
                id=self._id_string(req.id),
                delimiter=self._delimiter,
            )

    def table_exists(self, request: TableExistsRequest) -> None:
        req = _to_model(request, TableExistsRequest)
        with _translate_errors():
            return self._table_api.table_exists(
                id=self._id_string(req.id),
                table_exists_request=req,
                delimiter=self._delimiter,
            )

    def deregister_table(
        self, request: DeregisterTableRequest
    ) -> DeregisterTableResponse:
        req = _to_model(request, DeregisterTableRequest)
        with _translate_errors():
            return self._table_api.deregister_table(
                id=self._id_string(req.id),
                deregister_table_request=req,
                delimiter=self._delimiter,
            )

    def rename_table(self, request: RenameTableRequest) -> RenameTableResponse:
        req = _to_model(request, RenameTableRequest)
        with _translate_errors():
            return self._table_api.rename_table(
                id=self._id_string(req.id),
                rename_table_request=req,
                delimiter=self._delimiter,
            )

    def list_all_tables(self, request: ListTablesRequest) -> ListTablesResponse:
        req = _to_model(request, ListTablesRequest)
        with _translate_errors():
            return self._table_api.list_all_tables(
                delimiter=self._delimiter,
                page_token=req.page_token,
                limit=req.limit,
            )

    # Table version operations (called when the server returns
    # managed_versioning=true in describe/declare responses)

    def describe_table_version(
        self, request: DescribeTableVersionRequest
    ) -> DescribeTableVersionResponse:
        req = _to_model(request, DescribeTableVersionRequest)
        with _translate_errors():
            return self._table_api.describe_table_version(
                id=self._id_string(req.id),
                describe_table_version_request=req,
                delimiter=self._delimiter,
            )

    def create_table_version(
        self, request: CreateTableVersionRequest
    ) -> CreateTableVersionResponse:
        req = _to_model(request, CreateTableVersionRequest)
        with _translate_errors():
            return self._table_api.create_table_version(
                id=self._id_string(req.id),
                create_table_version_request=req,
                delimiter=self._delimiter,
            )

    def list_table_versions(
        self, request: ListTableVersionsRequest
    ) -> ListTableVersionsResponse:
        req = _to_model(request, ListTableVersionsRequest)
        with _translate_errors():
            return self._table_api.list_table_versions(
                id=self._id_string(req.id),
                delimiter=self._delimiter,
                branch=req.branch,
                page_token=req.page_token,
                limit=req.limit,
                descending=req.descending,
            )
