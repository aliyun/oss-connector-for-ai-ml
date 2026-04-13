# Core modules (no heavy dependencies - safe to import directly)
from .oss_checkpoint import OssCheckpoint
from ._oss_client import OssClient
from ._oss_connector import new_data_object
from ._oss_bucket_iterable import imagenet_manifest_parser
from ._oss_tar_iterable import generate_tar_archive

__all__ = [
    # Core (no heavy deps)
    "OssCheckpoint",
    "OssClient",
    "new_data_object",
    "imagenet_manifest_parser",
    "generate_tar_archive",
    # Torch-dependent (lazy)
    "OssIterableDataset",
    "OssMapDataset",
    "OssSafetensor",
    # Torch distributed checkpoint-dependent (lazy)
    "OssDCPFileSystem",
    "OssStorageReader",
    "OssStorageWriter",
    # Ultralytics-dependent (lazy)
    "OSSYOLODataset",
    "make_oss_trainer",
    # MMDetection-dependent (lazy)
    "OSSDetDataset",
    "OSSLoadImageFromFile",
    "get_oss_ann_path",
]


def __getattr__(name: str):
    """Lazy import for modules with heavy dependencies.

    This avoids forcing users to install torch, safetensors, or ultralytics
    when they only need core functionality like OssCheckpoint.
    """
    # Torch-dependent: OssIterableDataset, OssMapDataset
    if name == "OssIterableDataset":
        from .oss_iterable_dataset import OssIterableDataset
        return OssIterableDataset
    if name == "OssMapDataset":
        from .oss_map_dataset import OssMapDataset
        return OssMapDataset

    # Torch + safetensors-dependent: OssSafetensor
    if name == "OssSafetensor":
        from .oss_safetensor import OssSafetensor
        return OssSafetensor

    # Torch distributed checkpoint-dependent: OssDCPFileSystem, OssStorageReader, OssStorageWriter
    if name == "OssDCPFileSystem":
        from .oss_dcp_filesystem import OssDCPFileSystem
        return OssDCPFileSystem
    if name == "OssStorageReader":
        from .oss_dcp_filesystem import OssStorageReader
        return OssStorageReader
    if name == "OssStorageWriter":
        from .oss_dcp_filesystem import OssStorageWriter
        return OssStorageWriter

    # Ultralytics-dependent: OSSYOLODataset, make_oss_trainer
    if name == "OSSYOLODataset":
        from .integrations.ultralytics import OSSYOLODataset
        return OSSYOLODataset
    if name == "make_oss_trainer":
        from .integrations.ultralytics import make_oss_trainer
        return make_oss_trainer

    # MMDetection-dependent: OSSDetDataset, OSSLoadImageFromFile, get_oss_ann_path
    if name == "OSSDetDataset":
        from .integrations.mmdet import OSSDetDataset
        return OSSDetDataset
    if name == "OSSLoadImageFromFile":
        from .integrations.mmdet import OSSLoadImageFromFile
        return OSSLoadImageFromFile
    if name == "get_oss_ann_path":
        from .integrations.mmdet import get_oss_ann_path
        return get_oss_ann_path

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
