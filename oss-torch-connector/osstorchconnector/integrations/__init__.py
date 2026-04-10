"""
Framework-specific integrations for OSS data loading.

Each submodule provides drop-in replacements for popular ML frameworks:
- ultralytics: OSSYOLODataset, make_oss_trainer for YOLO training
- mmdet: OSSDetDataset, OSSLoadImageFromFile for MMDetection

All imports are lazy to avoid forcing dependency installation.
"""

__all__ = [
    # Ultralytics-dependent
    "OSSYOLODataset",
    "make_oss_trainer",
    # MMDetection-dependent
    "get_oss_ann_path",
    "OSSDetDataset",
    "OSSLoadImageFromFile",
]


def __getattr__(name: str):
    """Lazy import for framework-specific integrations."""
    # Ultralytics-dependent: OSSYOLODataset, make_oss_trainer
    if name == "OSSYOLODataset":
        from .ultralytics import OSSYOLODataset
        return OSSYOLODataset
    if name == "make_oss_trainer":
        from .ultralytics import make_oss_trainer
        return make_oss_trainer

    # MMDetection-dependent: get_oss_ann_path, OSSDetDataset, OSSLoadImageFromFile
    if name == "get_oss_ann_path":
        from .mmdet import get_oss_ann_path
        return get_oss_ann_path
    if name == "OSSDetDataset":
        from .mmdet import OSSDetDataset
        return OSSDetDataset
    if name == "OSSLoadImageFromFile":
        from .mmdet import OSSLoadImageFromFile
        return OSSLoadImageFromFile

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
