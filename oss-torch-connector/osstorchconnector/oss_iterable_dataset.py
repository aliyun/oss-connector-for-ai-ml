from functools import partial
from typing import Iterator, Any, Union, Iterable, Callable, Tuple
import io
import torch.utils.data
import uuid
import logging
import random

from ._oss_client import OssClient, DataObject
from ._oss_bucket_iterable import OssBucketIterable, identity
from ._oss_tar_iterable import OssTarIterable

log = logging.getLogger(__name__)

class OssIterableDataset(torch.utils.data.IterableDataset):
    """An IterableStyle dataset created from OSS objects.

    To create an instance of OssIterableDataset, you need to use
    `from_prefix`, `from_objects`, `from_manifest_file` or `from_tar` methods.
    """

    def __init__(
        self,
        endpoint: str,
        cred_path: str,
        config_path: str,
        get_dataset_objects: Callable[[OssClient], Iterable[DataObject]],
        transform: Callable[[DataObject], Any] = identity,
        cred_provider: Any = None,
        from_tar: bool = False,
        shuffle: bool = False,
        shuffle_chunk_size: int = 1000,
    ):
        self._uuid = uuid.uuid4()
        self._endpoint = endpoint
        log.info("OssIterableDataset init, uuid: %s, endpoint: %s", self._uuid, self._endpoint)
        if not endpoint:
            raise ValueError("endpoint must be non-empty")
        if not cred_path:
            self._cred_path = ""
        else:
            self._cred_path = cred_path
        self._cred_provider = cred_provider
        if not config_path:
            self._config_path = ""
        else:
            self._config_path = config_path
        self._get_dataset_objects = get_dataset_objects
        self._transform = transform
        self._client = None
        self._from_tar = from_tar
        self._shuffle = shuffle
        self._chunk_size = shuffle_chunk_size
        if from_tar and shuffle:
            self._bucket_objects = self._get_dataset_objects(self._get_client(0, 1), preload=False)
            self._dataset_size = len(self._bucket_objects)
            self.shuffle()
        else:
            self._bucket_objects = None

    @classmethod
    def from_objects(
        cls,
        object_uris: Union[str, Iterable[str]],
        endpoint: str,
        *,
        cred_path: str = "",
        cred_provider: Any = None,
        config_path: str = "",
        transform: Callable[[DataObject], Any] = identity,
    ):
        """Returns an instance of OssIterableDataset using the OSS URI(s) provided.

        Args:
          object_uris(str | Iterable[str]): OSS URI of the object(s) desired.
          endpoint(str): Endpoint of the OSS bucket where the objects are stored.
          cred_path(str): Credential info of the OSS bucket where the objects are stored.
          config_path(str): Configuration file path of the OSS connector.
          transform: Optional callable which is used to transform an DataObject into the desired type.
          cred_provider: OSS credential provider.

        Returns:
            OssIterableDataset: An IterableStyle dataset created from OSS objects.
        """
        log.info(f"Building {cls.__name__} from_objects")
        return cls(
            endpoint, cred_path, config_path, partial(OssBucketIterable.from_uris, object_uris, preload=True),
            transform=transform, cred_provider=cred_provider
        )

    @classmethod
    def from_prefix(
        cls,
        oss_uri: str,
        endpoint: str,
        *,
        cred_path: str = "",
        cred_provider: Any = None,
        config_path: str = "",
        transform: Callable[[DataObject], Any] = identity,
    ):
        """Returns an instance of OssIterableDataset using the OSS URI provided.

        Args:
          oss_uri(str): An OSS URI (prefix) of the object(s) desired. Objects matching the prefix will be included in the returned dataset.
          endpoint(str): Endpoint of the OSS bucket where the objects are stored.
          cred_path(str): Credential info of the OSS bucket where the objects are stored.
          config_path(str): Configuration file path of the OSS connector.
          transform: Optional callable which is used to transform an DataObject into the desired type.
          cred_provider: OSS credential provider.

        Returns:
            OssIterableDataset: An IterableStyle dataset created from OSS objects.
        """
        log.info(f"Building {cls.__name__} from_prefix")
        return cls(
            endpoint, cred_path, config_path, partial(OssBucketIterable.from_prefix, oss_uri, preload=True),
            transform=transform, cred_provider=cred_provider
        )

    @classmethod
    def from_manifest_file(
        cls,
        manifest_file_path: str,
        manifest_parser: Callable[[io.IOBase], Iterable[Tuple[str, str]]],
        oss_base_uri: str,
        endpoint: str,
        *,
        cred_path: str = "",
        cred_provider: Any = None,
        config_path: str = "",
        transform: Callable[[DataObject], Any] = identity,
    ):
        """Returns an instance of OssIterableDataset using manifest file provided.

        Args:
          manifest_file_path(str): OSS URI or local path of manifest file.
          manifest_parser: A callable which takes an io.IOBase object and returns an iterable of (object_uri, label).
          oss_base_uri(str): The base URI of the OSS object in manifest file.
          endpoint(str): Endpoint of the OSS bucket where the objects are stored.
          cred_path(str): Credential info of the OSS bucket where the objects are stored.
          config_path(str): Configuration file path of the OSS connector.
          transform: Optional callable which is used to transform an DataObject into the desired type.
          cred_provider: OSS credential provider.

        Returns:
            OssIterableDataset: An IterableStyle dataset created from OSS objects.
        """
        log.info(f"Building {cls.__name__} from_manifest_file")
        return cls(
            endpoint, cred_path, config_path, partial(OssBucketIterable.from_manifest_file, manifest_file_path, manifest_parser, oss_base_uri, preload=True),
            transform=transform, cred_provider=cred_provider
        )

    @classmethod
    def from_tar(
        cls,
        tar_uri: str,
        tar_index_uri: str,
        endpoint: str,
        *,
        cred_path: str = "",
        cred_provider: Any = None,
        config_path: str = "",
        transform: Callable[[DataObject], Any] = identity,
        shuffle: bool = False,
        shuffle_chunk_size: int = 1000,
    ):
        """Returns an instance of OssIterableDataset using tar file provided.

        Args:
          tar_uri(str): OSS URI of tar archive.
          tar_index_uri(str): OSS URI of tar index file corresponding to tar archive.
          shuffle(bool): Whether to shuffle the dataset.
          shuffle_chunk_size(int): Size of chunks to shuffle over.
          endpoint(str): Endpoint of the OSS bucket where the objects are stored.
          cred_path(str): Credential info of the OSS bucket where the objects are stored.
          config_path(str): Configuration file path of the OSS connector.
          transform: Optional callable which is used to transform an DataObject into the desired type.
          cred_provider: OSS credential provider.

        Returns:
            OssIterableDataset: An IterableStyle dataset created from tar file.
        """
        log.info(f"Building {cls.__name__} from_tar")
        return cls(
            endpoint, cred_path, config_path, partial(OssTarIterable.from_tar, tar_uri, tar_index_uri, preload=True),
            transform=transform, cred_provider=cred_provider, from_tar=True, shuffle=shuffle, shuffle_chunk_size=shuffle_chunk_size
        )

    def _get_client(self, id, total):
        if self._client is None:
            self._client = OssClient(self._endpoint, self._cred_path, self._config_path, self._uuid, id, total, cred_provider=self._cred_provider)
            log.info("OssIterableDataset new client")
        self._client._id = id
        self._client._total = total
        return self._client

    def _get_transformed_object(self, object: DataObject) -> Any:
        return self._transform(object)

    def __iter__(self) -> Iterator[Any]:
        worker_info = torch.utils.data.get_worker_info()

        if worker_info is None:     # single-process data loading, return the full iterator
            log.info("OssIterableDataset get iter (single-process)")
            if self._from_tar and self._shuffle:
                if len(self._chunks) >= 1:
                    chunks = self._chunks
                else:
                    chunks = []
                log.info("OssIterableDataset chunk num: %d", len(chunks))
                worker_iter = self._get_dataset_objects(self._get_client(0, 1), chunks=chunks)
            else:
                worker_iter = self._get_dataset_objects(self._get_client(0, 1))
        else:                       # in a worker process, split workload
            num_workers = worker_info.num_workers
            worker_id = worker_info.id
            log.info("OssIterableDataset get iter (multi-process), num_workers: %d, worker id: %d", num_workers, worker_id)
            if self._from_tar and self._shuffle:
                if len(self._chunks) >= num_workers:
                    chunks = [chunk for i, chunk in enumerate(self._chunks) if i % num_workers == worker_id]
                else:
                    chunks = []
                log.info("OssIterableDataset chunk num: %d", len(chunks))
                worker_iter = self._get_dataset_objects(self._get_client(worker_id, num_workers), chunks=chunks)
            else:
                worker_iter = self._get_dataset_objects(self._get_client(worker_id, num_workers))

        return map(self._get_transformed_object, worker_iter)

    def shuffle(self, generator=None):
        if generator is None:
            seed = int(torch.empty((), dtype=torch.int64).random_().item())
            generator = torch.Generator()
            generator.manual_seed(seed)
            log.debug("OssIterableDataset shuffle seed: %d", seed)
        chunks = []
        index = 0
        while index < self._dataset_size:
            chunk_size = min(max(1, int(random.gauss(self._chunk_size, 10))), self._dataset_size - index)
            chunks.append((index, chunk_size))
            index += chunk_size
        random_sampler = torch.utils.data.SubsetRandomSampler(chunks, generator=generator)
        self._chunks = list(random_sampler)
        log.info("OssIterableDataset shuffle chunk indices, dataset size: %d, chunk num: %d",
                 self._dataset_size, len(self._chunks))
