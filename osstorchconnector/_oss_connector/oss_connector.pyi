from typing import Iterable, Iterator


class DataObject:
    key: str
    size: int
    label: str

    def __enter__(self) -> DataObject: ...
    def __exit__(self, exc_type, exc_val, exc_tb): ...
    def tell(self) -> int: ...
    def seek(self, offset: int, whence: int) -> int: ...
    def read(self, count: int) -> bytes: ...
    def readinto(self, buf) -> int: ...
    def write(self, data) -> int: ...
    def close(self) -> int: ...
    def flush(self) -> int: ...
    def err(self) -> int: ...
    def error_msg(self) -> str: ...
    def copy(self) -> DataObject: ...


class DataSet:
    def list(self, bucket: str, prefix: str) -> Iterator[DataObject]: ...
    def list_with_preload(self, bucket: str, prefix: str) -> Iterator[DataObject]: ...
    def list_from_uris(self, iter: Iterable, prefetch: bool, include_errors: bool) -> Iterator[DataObject]: ...
    def list_from_uris_with_preload(self, iter: Iterable) -> Iterator[DataObject]: ...
    def open_ro(self, bucket: str, key: str, size: int, mmap: int, label: str) -> DataObject: ...
    def open_wo(self, bucket: str, key: str) -> DataObject: ...


def new_oss_dataset(endpoint: str, cred_path: str, config_path: str, uuid: str, id: int, total: int) -> DataSet:
    ...


def new_data_object(key: str, size: int, label: str) -> DataObject:
    ...
