from ._oss_bucket_iterable import parse_oss_uri
from ._oss_client import OssClient, DataObject
from ctypes import *

class OssCheckpoint:
    """A checkpoint manager for OSS.

    To read a checkpoint from OSS, users need to create an `DataObject`
    by providing oss_uri of the checkpoint stored in OSS. Similarly, to save a
    checkpoint to OSS, users need to create an `DataObject` by providing oss_uri.
    `DataObject` can be passed to torch.load, and torch.save.
    """

    def __init__(
        self,
        endpoint: str,
        cred_path: str = "",
        config_path: str = "",
    ):
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
        self._client = OssClient(self._endpoint, self._cred_path, self._config_path)

    def reader(self, oss_uri: str):
        """Creates an DataObject from a given oss_uri.

        Args:
            oss_uri (str): A valid oss_uri. (i.e. oss://<BUCKET>/<KEY>)

        Returns:
            DataObject: a read-only binary stream of the OSS object's contents, specified by the oss_uri.
        """
        bucket, key = parse_oss_uri(oss_uri)
        return self._client.get_object(bucket, key, type=1)

    def writer(self, oss_uri: str) -> DataObject:
        """Creates an DataObject from a given oss_uri.

        Args:
            oss_uri (str): A valid oss_uri. (i.e. oss://<BUCKET>/<KEY>)

        Returns:
            DataObject: a write-only binary stream. The content is saved to OSS using the specified oss_uri.
        """
        bucket, key = parse_oss_uri(oss_uri)
        return self._client.put_object(bucket, key)
