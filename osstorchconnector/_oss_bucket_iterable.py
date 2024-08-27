from typing import Iterator, Iterable, Union, Tuple, Callable
from ._oss_client import OssClient, DataObject
from ._oss_connector import new_data_object
import logging
import io

log = logging.getLogger(__name__)

def identity(obj: DataObject) -> DataObject:
    if obj is not None:
        return obj.copy()
    else:
        return None

def parse_oss_uri(uri: str) -> Tuple[str, str]:
    if not uri or not (uri.startswith("oss://") or uri.startswith("/")):
        raise ValueError("Only oss:// URIs are supported")
    if uri.startswith("oss://"):
        uri = uri[len("oss://"):]
    elif uri.startswith("/"):
        uri = uri[1:]
    if not uri:
        raise ValueError("Bucket name must be non-empty")
    split = uri.split("/", maxsplit=1)
    if len(split) == 1:
        bucket = split[0]
        prefix = ""
    else:
        bucket, prefix = split
    if not bucket:
        raise ValueError("Bucket name must be non-empty")
    return bucket, prefix

def imagenet_manifest_parser(reader: io.IOBase) -> Iterable[Tuple[str, str]]:
    lines = reader.read().decode("utf-8").strip().split("\n")
    for i, line in enumerate(lines):
        try:
            items = line.strip().split('\t')
            if len(items) >= 2:
                key = items[0]
                label = items[1]
                yield (key, label)
            elif len(items) == 1:
                key = items[0]
                yield (key, '')
            else:
                raise ValueError("format error")
        except ValueError as e:
            logging.error(f"Error: {e} for line {i}: {line}")


class OssBucketIterable:
    def __init__(self, client: OssClient, *,
                 oss_uri: str = None,
                 object_uris: Iterable[str] = None,
                 preload: bool = False,
                 manifest_file_path: str = None,
                 manifest_parser: Callable[[io.IOBase], Iterable[Tuple[str, str]]] = None,
                 oss_base_uri: str = None):
        log.info("OssBucketIterable init")
        self._client = client
        self._oss_uri = oss_uri
        self._object_uris = object_uris
        self._preload = preload
        self._manifest_file_path = manifest_file_path
        self._manifest_parser = manifest_parser
        self._oss_base_uri = oss_base_uri
        self._data_objects: Iterable[DataObject] = None

    @classmethod
    def from_uris(cls, object_uris: Union[str, Iterable[str]], client: OssClient, preload: bool = False):
        if not object_uris:
            raise ValueError("object_uris must be non-empty")
        if isinstance(object_uris, str):
            object_uris = [object_uris]
        return cls(client, object_uris=object_uris, preload=preload)

    @classmethod
    def from_prefix(cls, oss_uri: str, client: OssClient, preload: bool = False):
        if not oss_uri:
            raise ValueError("oss_uri must be non-empty")
        if not oss_uri.startswith("oss://"):
            raise ValueError("only oss:// uri are supported")
        return cls(client, oss_uri=oss_uri, preload=preload)

    @classmethod
    def from_manifest_file(cls, manifest_file_path: str, manifest_parser: Callable[[io.IOBase], Iterable[Tuple[str, str]]],
                   oss_base_uri: str, client: OssClient, preload: bool = False):
        if not manifest_file_path:
            raise ValueError("manifest_file_path must be non-empty")
        if not manifest_parser:
            raise ValueError("manifest_parser must be non-empty")
        return cls(client, manifest_file_path=manifest_file_path, manifest_parser=manifest_parser,
                   oss_base_uri=oss_base_uri, preload=preload)

    def _get_data_object_by_manifest(self) -> Iterator[DataObject]:
        if self._manifest_file_path.startswith("oss://"):
            ibucket, ikey = parse_oss_uri(self._manifest_file_path)
            with self._client.get_object(ibucket, ikey, type=0) as manifest_file:
                for key, label in self._manifest_parser(manifest_file):
                    yield new_data_object(self._oss_base_uri + key, 0, label)
        else:
            with open(self._manifest_file_path, "rb") as manifest_file:
                for key, label in self._manifest_parser(manifest_file):
                    yield new_data_object(self._oss_base_uri + key, 0, label)

    def __iter__(self) -> Iterator[DataObject]:
        # This allows us to iterate multiple times by re-creating the `_list_stream`
        if self._object_uris is not None:
            log.info("OssBucketIterable get iter by object uris")
            self._data_objects = [new_data_object(uri, 0, "") for uri in self._object_uris]
            return iter(OssBucketObjectsIterator(self._client, self._data_objects, self._preload))
        elif self._manifest_file_path is not None and self._manifest_parser is not None:
            log.info("OssBucketIterable get iter by manifest file: %s", self._manifest_file_path)
            self._data_objects = self._get_data_object_by_manifest()
            return iter(OssBucketObjectsIterator(self._client, self._data_objects, self._preload))
        elif self._oss_uri is not None:
            log.info("OssBucketIterable get iter by oss prefix: %s", self._oss_uri)
            return iter(OssBucketPrefixIterator(self._client, self._oss_uri, self._preload))
        else:
            log.error("OssBucketIterable get iter failed")
            return None


class OssBucketObjectsIterator:
    def __init__(self, client: OssClient, objects: Iterable[DataObject], preload: bool) -> Iterator[DataObject]:
        log.info("OssBucketObjectsIterator init")
        if preload:
            self._list_stream = iter(client.list_objects_from_uris_with_preload(objects))
        else:
            self._list_stream = iter(objects) # map does not need pass objects to client for now

    def __iter__(self) -> Iterator[DataObject]:
        log.info("OssBucketObjectsIterator get iter")
        return self._list_stream


class OssBucketPrefixIterator:
    def __init__(self, client: OssClient, oss_uri: str, preload: bool):
        log.info("OssBucketPrefixIterator init")
        bucket, prefix = parse_oss_uri(oss_uri)
        if preload:
            self._list_stream = iter(client.list_objects_with_preload(bucket, prefix))
        else:
            self._list_stream = iter(client.list_objects(bucket, prefix))

    def __iter__(self) -> Iterator[DataObject]:
        log.info("OssBucketPrefixIterator get iter")
        return self._list_stream
