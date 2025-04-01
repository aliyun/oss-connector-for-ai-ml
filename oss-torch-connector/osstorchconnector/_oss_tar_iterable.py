from typing import Iterator, List, Tuple, Any
from ._oss_client import OssClient, DataObject
from ._oss_bucket_iterable import parse_oss_uri
import logging

log = logging.getLogger(__name__)

class OssTarIterable:
    def __init__(self, client: OssClient, *,
                 tar_uri: str = None,
                 tar_index_uri: str = None,
                 preload: bool = False,
                 chunks: List[Tuple[int, int]] = []):
        log.info("OssTarIterable init, preload: %s", preload)
        self._client = client
        self._tar_uri = tar_uri
        self._tar_index_uri = tar_index_uri
        self._preload = preload
        self._chunks = chunks
        self._list_stream = None

    @classmethod
    def from_tar(cls, tar_uri: str, tar_index_uri: str, client: OssClient, preload: bool = False,
                 chunks: List[Tuple[int, int]] = []):
        if not tar_uri:
            raise ValueError("tar_uri must be non-empty")
        if not tar_uri.startswith("oss://"):
            raise ValueError("only oss:// uri are supported for tar_uri")
        if not tar_index_uri:
            raise ValueError("tar_index_uri must be non-empty")
        if not tar_index_uri.startswith("oss://"):
            raise ValueError("only oss:// uri are supported for tar_index_uri")
        return cls(client, tar_uri=tar_uri, tar_index_uri=tar_index_uri, preload=preload,
                   chunks=chunks)

    def __iter__(self) -> Iterator[DataObject]:
        # This allows us to iterate multiple times by re-creating the `_list_stream`
        self._list_stream = OssTarObjectsIterator(self._client, self._tar_uri, self._tar_index_uri, self._preload,
                                                  chunks=self._chunks)
        return iter(self._list_stream)

    def __len__(self):
        if self._list_stream is None:
            self._list_stream = OssTarObjectsIterator(self._client, self._tar_uri, self._tar_index_uri, self._preload,
                                                      chunks=self._chunks)
        return len(self._list_stream)


class OssTarObjectsIterator:
    def __init__(self, client: OssClient, tar_uri: str, tar_index_uri: str, preload: bool,
                 chunks: List[Tuple[int, int]] = []):
        log.info("OssTarObjectsIterator init")
        tar_bucket, tar_key = parse_oss_uri(tar_uri)
        index_bucket, index_key = parse_oss_uri(tar_index_uri)
        if tar_bucket != index_bucket:
            raise ValueError("tar_uri and tar_index_uri must be in the same bucket")
        starts = [start for start, _ in chunks] if chunks else []
        sizes = [size for _, size in chunks] if chunks else []
        self._list_stream = client.list_objects_from_tar(tar_bucket, tar_key, index_key, prefetch=preload,
                                                         chunks=starts, sizes=sizes)

    def __iter__(self) -> Iterator[DataObject]:
        log.info("OssTarObjectsIterator get iter")
        return iter(self._list_stream)

    def __len__(self):
        return len(self._list_stream)


def generate_tar_archive(endpoint: str, cred_path: str, config_path: str, tar_path: str,
                         index_path: str, source_path: str, index_only: bool = False,
                         cred_provider: Any = None):
    """ Generate tar archive and its index.

        Args:
          endpoint(str): Endpoint of the OSS bucket where the objects are stored.
          cred_path(str): Credential info of the OSS bucket where the objects are stored.
          config_path(str): Configuration file path of the OSS connector.
          tar_path(str): Path to the tar archive. (OSS URI or local path)
          index_path(str): Path to the tar index. (OSS URI or local path)
          source_path(str): Path to the source directory. (OSS URI or local path)
          index_only(bool): If True, generate tar index from tar archive specified by 'tar_path',
                            otherwise (by default) generate tar archive and its index from
                            source directory specified by 'source_path'.
          cred_provider: OSS credential provider.
    """
    if not endpoint:
        raise ValueError("endpoint must be non-empty")
    if not cred_path and not cred_provider:
        raise ValueError("neither cred_path nor cred_provider is specified")
    client = OssClient(endpoint, cred_path, config_path, cred_provider=cred_provider)
    return client.gen_tar_archive(tar_path, index_path, source_path, index_only)
