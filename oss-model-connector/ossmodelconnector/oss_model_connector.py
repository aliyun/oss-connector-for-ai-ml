from ._oss_connector import new_oss_connector, Connector
import ctypes
import torch
import builtins
import pathlib
from typing import Any


class UntypedStorageEx:
    def __init__(self, file, size):
        self.file = file
        self.addr = memoryview((ctypes.c_ubyte * size).from_address(self.file.mmap()))

    def untyped(self):
        return self

    def __getitem__(self, idx):
        return self.addr[idx]

class OssModelConnector:
    """
    A connector class for interfacing with OSS for model loading,
    providing high-performance methods to load models/objects/files for AI inference.
    """

    def __init__(
        self,
        endpoint: str,
        cred_path: str = "",
        config_path: str = "",
        cred_provider: Any = None,
    ):
        """
        Initializes the connector with endpoint and optional credential information.

        Args:
            endpoint(str): The OSS endpoint to connect to.
            cred_path(str, optional): Path to the credential file. Defaults to "".
            config_path(str, optional): Path to the configuration file. Defaults to "".
            cred_provider(Any, optional): Credential provider. Defaults to None.

        Raises:
            ValueError: If endpoint or credential is not provided.
        """
        if not endpoint:
            raise ValueError("endpoint must be non-empty")
        if cred_provider is None and not cred_path:
            raise ValueError("Either cred_path or cred_provider must be provided")

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

        self._real_connector = None
        self._hook_dir = ''
        self._origin_from_file = torch.UntypedStorage.from_file
        self._origin_open = builtins.open

    def __del__(self):
        self.close()
    @property
    def _connector(self):
        if self._real_connector is None:
            if self._cred_provider is not None:
                self._real_connector = new_oss_connector(self._endpoint, self._cred_provider, self._config_path)
            else:
                self._real_connector = new_oss_connector(self._endpoint, self._cred_path, self._config_path)

        return self._real_connector

    def close(self):
        """
        Close the connector and release resources.
        """
        try:
            if self._hook_dir:
                self._hook_dir = ''

            if builtins.open == self._connector_open:
                builtins.open = self._origin_open

            if torch.UntypedStorage.from_file == self._from_file_helper:
                torch.UntypedStorage.from_file = self._origin_from_file

            if self._real_connector is not None:
                del self._real_connector
                self._real_connector = None
        except:
            print("exception in close, ignore")

    def open(self, uri, binary = True):
        """
        Opens an object from OSS storage.

        Args:
            uri(str): The uri (oss://{bucket}/{object_name}) of the object to open.
            binary(bool): Flag indicating whether to open in binary mode or not.

        Returns:
            Stream-like object of the opened OSS object.
        """
        return self._connector.open(uri, True, True, binary)

    def _from_file_helper(self, filename, shared, nbytes):
        if self._hook_dir and filename.startswith(self._hook_dir):
            file = self._connector.open(filename, True, True)
            return UntypedStorageEx(file, nbytes)
        else:
            return self._origin_from_file(filename, shared, nbytes)

    def _connector_open(self, file, mode='r', buffering=-1, encoding=None, errors=None, newline=None, closefd=True, opener=None):
        if isinstance(file, pathlib.Path):
            file = str(file)
        if self._hook_dir and file.startswith(self._hook_dir):
            binary = False
            if 'b' in mode:
                binary = True
            try:
                return self.open(file, binary)
            except:
                return self._origin_open(file, mode, buffering, encoding, errors, newline, closefd, opener)
        else:
            return self._origin_open(file, mode, buffering, encoding, errors, newline, closefd, opener)

    def prepare_directory(self, uri: str, dir: str, libc_hook: bool = False):
        """
        Prepare the directory from OSS storage, which can be used as directory 'dir' in vllm/transformers or other frameworks.

        Args:
            uri(str): The URI (oss://{bucket}/{directory}) of the OSS directory.
            dir(str): The local directory used for vllm/transformers or other frameworks.
            libc_hook (bool): Flag to enable libc hooking.

        Raises:
            RuntimeError: If prepare directory failed.
        """
        if not dir.endswith('/'):
            dir += '/'
        self._connector.prepare_directory(uri, dir, libc_hook)
        if not libc_hook:
            builtins.open = self._connector_open
            torch.UntypedStorage.from_file = self._from_file_helper
            self._hook_dir = dir

    def list(self, bucket: str, prefix: str, fast: bool = False):
        """
        Lists objects in a specified OSS bucket with a given prefix.

        Args:
            bucket(str): The OSS bucket name.
            prefix(str): The prefix filter for object listing.
            fast (bool): If true, enables fast list mode.

        Returns:
            List: A list of objects matching the bucket and prefix criteria.
        """
        return self._connector.list(bucket, prefix, fast)
