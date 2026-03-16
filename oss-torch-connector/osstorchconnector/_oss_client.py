import os
from typing import Iterator, Iterable, Any
import logging
import threading

log = logging.getLogger(__name__)

from ._oss_connector import (
    DataSet,
    DataObject,
    new_oss_dataset
)

O_MULTI_PART = 0x40000000   # oss multi-part upload

"""
_oss_client.py
    Internal client wrapper class on top of OSS client interface
    with multi-process support.
"""

class OssClient:
    def __init__(
        self,
        endpoint: str,
        cred_path: str = "",
        config_path: str = "",
        uuid: str = "",
        id: int = 0,
        total: int = 1,
        cred_provider: Any = None,
        region: str = "",
    ):
        self._endpoint = endpoint if endpoint else ""
        self._cred_path = cred_path
        self._config_path = config_path
        self._uuid = uuid
        self._real_client = None
        self._client_pid = None
        self._id = id
        self._total = total
        self._cred_provider = cred_provider
        self._region = region

    _lock = threading.Lock()
    @property
    def _client(self) -> DataSet:
        with OssClient._lock:
            if self._client_pid is None or self._client_pid != os.getpid() :
                # does OSS client survive forking ? NO
                if self._client_pid != os.getpid() and self._real_client is not None:
                    log.info("OssClient delete dataset")
                    # del self._real_client
                self._client_pid = os.getpid()
                self._real_client = self._client_builder()

        return self._real_client

    def _client_builder(self) -> DataSet:
        log.info("OssClient new_oss_dataset, id %d, total %d", self._id, self._total)
        return new_oss_dataset(self._endpoint, self._cred_path, self._cred_provider, self._config_path, str(self._uuid), self._id, self._total, self._region)

    def get_object(self, bucket: str, key: str, size: int = 0, type: int = 0, label: str = "") -> DataObject:
        return self._client.open_ro(bucket, key, size, type, label)

    def put_object(self, bucket: str, key: str) -> DataObject:
        return self._client.open_wo(bucket, key)

    def head_object(self, bucket: str, key: str) -> DataObject:
        return self._client.stat(bucket, key)

    def rename_object(self, bucket: str, key: str, new_bucket: str, new_key: str) -> DataObject:
        return self._client.rename(bucket, key, new_bucket, new_key)

    def remove_object(self, bucket: str, key: str):
        return self._client.remove(bucket, key)

    def list_objects(self, bucket: str, prefix: str = "") -> Iterator[DataObject]:
        log.debug("OssClient list_objects")
        return self._client.list(bucket, prefix)

    def list_objects_with_preload(self, bucket: str, prefix: str = "", include_errors: bool = False) -> Iterator[DataObject]:
        log.debug("OssClient list_objects_with_preload")
        return self._client.list_with_preload(bucket, prefix, include_errors)

    def list_objects_from_uris(self, object_uris: Iterable, prefetch: bool = False, include_errors: bool = False) -> Iterator[DataObject]:
        log.debug("OssClient list_objects_from_uris")
        return self._client.list_from_uris(object_uris, prefetch, include_errors)

    def list_objects_from_uris_with_preload(self, object_uris: Iterable, include_errors: bool = False) -> Iterator[DataObject]:
        log.debug("OssClient list_objects_from_uris_with_preload")
        return self._client.list_from_uris_with_preload(object_uris, include_errors)

    def list_objects_from_tar(self, bucket: str, tar_key: str, index_key: str, chunks: Iterable = [], sizes: Iterable = [],
                              prefetch: bool = False, include_errors: bool = False) -> Iterator[DataObject]:
        log.debug("OssClient list_objects_from_tar")
        return self._client.list_from_tar(bucket, tar_key, index_key, chunks, sizes, prefetch, include_errors)

    def gen_tar_archive(self, tar_path: str, index_path: str, source_path: str, index_only: bool = False) -> int:
        return self._client.gen_tar_archive(tar_path, index_path, source_path, index_only)
