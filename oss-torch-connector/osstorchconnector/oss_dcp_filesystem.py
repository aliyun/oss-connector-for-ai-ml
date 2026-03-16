import io
import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Union, Any
from ._oss_client import OssClient
from ._oss_bucket_iterable import parse_oss_uri


from torch.distributed.checkpoint.filesystem import (
    FileSystemReader,
    FileSystemWriter,
    FileSystemBase,
)

logger = logging.getLogger(__name__)

class OssStorageWriter(FileSystemWriter):
    def __init__(
        self,
        fs,
        path: str,
        **kwargs,
    ) -> None:
        """
        Initialize an OSS writer for distributed checkpointing.

        Args:
            endpoint (str): Endpoint of the OSS bucket where the objects are stored.
            path (Union[str, os.PathLike]): The OSS URI to write checkpoints to.
            cred_path (str): Credential info of the OSS bucket where the objects are stored.
            config_path (str): Configuration file path of the OSS connector.
            cred_provider: OSS credential provider.
        """
        super().__init__(
            path=path,
            sync_files=False,
            **kwargs,
        )
        self.fs = fs
        self.path = self.fs.init_path(path)

    @classmethod
    def validate_checkpoint_id(cls, checkpoint_id: Union[str, os.PathLike]) -> bool:
        return OssDCPFileSystem.validate_checkpoint_id(checkpoint_id)

class OssStorageReader(FileSystemReader):
    def __init__(
        self,
        fs,
        path: str
    ) -> None:
        """
        Initialize an OSS reader for distributed checkpointing.

        Args:
            endpoint (str): Endpoint of the OSS bucket where the objects are stored.
            path (Union[str, os.PathLike]): The OSS path to read checkpoints from.
            cred_path (str): Credential info of the OSS bucket where the objects are stored.
            config_path (str): Configuration file path of the OSS connector.
            cred_provider: OSS credential provider.
        """
        super().__init__(path)
        self.fs = fs
        self.path = self.fs.init_path(path)
        self.sync_files = False

    @classmethod
    def validate_checkpoint_id(cls, checkpoint_id: Union[str, os.PathLike]) -> bool:
        return OssDCPFileSystem.validate_checkpoint_id(checkpoint_id)

class OssDCPFileSystem(FileSystemBase):
    def __init__(
        self,
        endpoint: str,
        cred_path: str = "",
        config_path: str = "",
        cred_provider: Any = None,
        region: str = "",
    ):
        """
        Initialize an FileSystem for distributed checkpointing.
        OssDCPFileSystem is intended for DCP only and is not a full-featured FileSystem.

        Args:
            endpoint (str): Endpoint of the OSS bucket where the objects are stored.
            cred_path (str): Credential info of the OSS bucket where the objects are stored.
            config_path (str): Configuration file path of the OSS connector.
            cred_provider: OSS credential provider.
            region(str): OSS region. Region will be inferred from 'endpoint' if not set, but this may fail when the endpoint lacks region information.
        """
        if not endpoint:
            raise ValueError("endpoint must be non-empty")
        else:
            self._endpoint = endpoint
        if not cred_path:
            self._cred_path = ""
        else:
            self._cred_path = cred_path
        if not config_path:
            self._config_path = ""
        else:
            self._config_path = config_path
        self._cred_provider = cred_provider
        self._region = region
        self._client = OssClient(self._endpoint, self._cred_path, self._config_path, cred_provider=self._cred_provider, region=self._region)
        self._path: Union[str, os.PathLike] = ""

    @contextmanager
    def create_stream(
        self, path: Union[str, os.PathLike], mode: str
    ) -> Generator[io.IOBase, None, None]:
        path_str = _parse_path(path)
        bucket, key = parse_oss_uri(path_str)

        if mode == "wb":
            logger.debug("create_stream writable for %s", path_str)
            with self._client.put_object(bucket, key) as stream:
                yield stream
        elif mode == "rb":
            logger.debug("create_stream readable for %s", path_str)
            with self._client.get_object(bucket, key, type=1) as stream:
                yield stream
        else:
            raise ValueError(
                f"Invalid mode argument: only rb/wb are supported"
            )

    def concat_path(self, path: Union[str, os.PathLike], suffix: str) -> str:
        logger.debug("concat paths %s and %s", path, suffix)
        path_str = os.fspath(path)
        return os.path.join(path_str, suffix)

    def init_path(self, path: Union[str, os.PathLike]) -> Union[str, os.PathLike]:
        logger.debug("init_path for %s", path)
        self._path = path
        return self._path

    def rename(
        self, old_path: Union[str, os.PathLike], new_path: Union[str, os.PathLike]
    ) -> None:
        logger.debug("rename %s to %s", old_path, new_path)
        old_bucket, old_key = parse_oss_uri(_parse_path(old_path))
        new_bucket, new_key = parse_oss_uri(_parse_path(new_path))
        self._client.rename_object(old_bucket, old_key, new_bucket, new_key)

    def mkdir(self, path: Union[str, os.PathLike]) -> None:
        logger.debug("mkdir %s", path)
        pass

    def exists(self, path: Union[str, os.PathLike]) -> bool:
        logger.debug("exists %s", path)
        bucket, key = parse_oss_uri(_parse_path(path))
        try:
            self._client.head_object(bucket, key)
        except Exception:
            return False
        return True

    def rm_file(self, path: Union[str, os.PathLike]) -> None:
        logger.debug("remove %s", path)
        bucket, key = parse_oss_uri(_parse_path(path))
        self._client.remove_object(bucket, key)

    @classmethod
    def validate_checkpoint_id(cls, checkpoint_id: Union[str, os.PathLike]) -> bool:
        logger.debug("validate_checkpoint_id for %s", checkpoint_id)

        if isinstance(checkpoint_id, Path):
            return True

        try:
            parse_oss_uri(_parse_path(checkpoint_id))
        except ValueError:
            return False
        return True

    def writer(self, path : str, **kwargs) -> OssStorageWriter:
        return OssStorageWriter(self, path, **kwargs)

    def reader(self, path : str) -> OssStorageReader:
        return OssStorageReader(self, path)

def _parse_path(path: Union[str, os.PathLike]) -> str:
    return path if isinstance(path, str) else str(path)
