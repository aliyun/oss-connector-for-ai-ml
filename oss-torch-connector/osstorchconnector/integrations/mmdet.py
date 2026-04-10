"""
OSS MMDetection Dataset — inherits CocoDataset for OSS-backed training.

Minimal override strategy:
  CocoDataset → BaseDetDataset already handles:
    - load_data_list()   (COCO JSON → data_list via COCO API)
    - parse_data_info()  (builds img_path, instances, etc.)
    - filter_data()      (filter_cfg: filter_empty_gt, min_size)
    - METAINFO           (80 COCO class names + palette)

  OSSDetDataset only adds:
    __init__      — download ann_file (COCO JSON) from OSS to a local temp
                    file; pass the local path to super().__init__() so the
                    inherited load_data_list() can read it normally.
                    data_root remains oss://, so _join_prefix() correctly
                    expands data_prefix → full OSS URI used as img_path.
    get_data_info — inject 'oss_dataset': self after deserialization, so
                    OSSLoadImageFromFile can access the OSS client and
                    prefetch cache.

Registered in mmdet's registry (default_scope='mmdet').

Data flow:
  data_root   = 'oss://bucket/COCO'
  ann_file    = 'annotations/instances_train2017.json'   ← downloaded to /tmp
  data_prefix = dict(img='train2017/')

  _join_prefix():
    data_prefix['img'] = join('oss://bucket/COCO', 'train2017/')
                       = 'oss://bucket/COCO/train2017/'

  parse_data_info() [inherited]:
    img_path = join(data_prefix['img'], file_name)
             = 'oss://bucket/COCO/train2017/000001.jpg'

  OSSLoadImageFromFile:
    bucket, key = parse_oss_uri(img_path)
    img_bytes   = client.get_object(bucket, key, 0, type=2).read()
    img = mmcv.imfrombytes(img_bytes, ...)

Config usage (mmdetection RTMDet):
  train_dataloader = dict(
      dataset=dict(
          type='OSSDetDataset',
          data_root='oss://your-bucket/COCO',
          ann_file='annotations/instances_train2017.json',
          data_prefix=dict(img='train2017/'),
          oss_endpoint='https://oss-cn-your-region.aliyuncs.com',
          oss_cred_path='/path/to/credentials',
          oss_config_path='/path/to/config.json',
          filter_cfg=dict(filter_empty_gt=True, min_size=32),
          pipeline=train_pipeline,
      )
  )
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any, List, Optional

import mmcv
import numpy as np
from mmcv.transforms import LoadImageFromFile as _LoadImageFromFile
from mmdet.datasets import CocoDataset
from mmdet.registry import DATASETS, TRANSFORMS
from mmengine.logging import print_log

from .._oss_bucket_iterable import parse_oss_uri
from .._oss_client import OssClient
from .._oss_connector import new_data_object


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def get_oss_ann_path(
    data_root: str,
    ann_file: str,
    ann_cache_dir: str = "/tmp",
) -> tuple[str, str, str]:
    """Compute the OSS bucket, key, and local cache path for an annotation file.

    Args:
        data_root: OSS URI root, e.g. ``'oss://bucket/COCO'``.
        ann_file: COCO JSON annotation file path relative to data_root,
            e.g. ``'annotations/instances_train2017.json'``.
        ann_cache_dir: Local directory to cache downloaded annotations.
            Default: ``'/tmp'``.

    Returns:
        (bucket, key, local_path) where:
            bucket     – OSS bucket name, e.g. ``'bucket'``.
            key        – OSS object key, e.g.
                         ``'COCO/annotations/instances_train2017.json'``.
            local_path – Deterministic local cache path, e.g.
                         ``'/tmp/oss_ann_bucket_COCO_annotations_instances_train2017.json'``.
    """
    ann_key = f"{data_root.rstrip('/')}/{ann_file.lstrip('/')}"
    bucket, key = parse_oss_uri(ann_key)
    # Deterministic local path
    local_path = os.path.join(
        ann_cache_dir, f"oss_ann_{bucket}_{key.replace('/', '_')}"
    )
    return bucket, key, local_path


@DATASETS.register_module()
class OSSDetDataset(CocoDataset):
    """OSS-backed detection dataset for MMDetection, built on CocoDataset.

    Downloads the COCO JSON annotation file from OSS to a local temp path
    before delegating to the parent class for all data loading and parsing.
    Images are read from OSS at training time via OSSLoadImageFromFile.

    Args:
        data_root (str): OSS URI root, e.g. ``'oss://bucket/COCO'``.
        ann_file (str): COCO JSON annotation file path relative to data_root,
            e.g. ``'annotations/instances_train2017.json'``. Downloaded from
            OSS during dataset initialisation.
        data_prefix (dict): Image directory prefix relative to data_root,
            e.g. ``dict(img='train2017/')``.  After ``_join_prefix()``,
            this becomes ``'oss://bucket/COCO/train2017/'``, which is joined
            with each ``file_name`` from the COCO JSON by the inherited
            ``parse_data_info()`` to produce the full OSS img_path.
        oss_endpoint (str): OSS service endpoint URL.
        oss_cred_path (str): Path to OSS credentials file. Default: ``''``.
        oss_config_path (str): Path to OSS config JSON file. Default: ``''``.
        oss_cred_provider (Any): OSS credential provider. Default: ``None``.
        oss_region (str): OSS region. Default: ``''``.
        **kwargs: Forwarded to :class:`CocoDataset`
            (``pipeline``, ``filter_cfg``, ``indices``, …).

    Inherited from CocoDataset (no override needed):
        METAINFO      – 80 COCO class names and palette
        load_data_list – parses the downloaded COCO JSON via COCO API
        parse_data_info – builds img_path, instances (xyxy bbox, bbox_label)
        filter_data    – applies filter_cfg (filter_empty_gt, min_size)
    """

    def __init__(
        self,
        data_root: str,
        ann_file: str,
        oss_endpoint: str,
        oss_cred_path: str = "",
        oss_config_path: str = "",
        oss_cred_provider: Any = None,
        oss_region: str = "",
        ann_cache_dir: str = "/tmp",
        **kwargs,
    ):
        # ── OSS params — must be set before _download_ann_file ───────────────
        self._endpoint      = oss_endpoint
        self._cred_path     = oss_cred_path
        self._config_path   = oss_config_path
        self._cred_provider = oss_cred_provider
        self._region        = oss_region
        self._uuid       = uuid.uuid4()
        self._client: Optional[OssClient] = None
        self._client_pid: Optional[int]   = None

        # ── Parse oss://bucket/base_key ─────────────────────────────────────
        if not data_root.startswith("oss://"):
            raise ValueError(f"data_root must start with 'oss://', got: {data_root!r}")
        self._data_root = data_root
        self._ann_cache_dir = ann_cache_dir
        os.makedirs(ann_cache_dir, exist_ok=True)

        # ── Prefetch buffer (idx-keyed, FIFO eviction) ───────────────────────
        # self._objects     : dict[int, DataObject]  idx → preloaded OSS object
        # self._buffered_idx: list[int]              insertion-ordered buffer
        # self._max_buffer  : int                    eviction threshold
        # Eviction mirrors base.py: pop oldest idx when buffer exceeds capacity.
        self._objects: dict[int, Any] = {}
        self._buffered_idx: list[int] = []
        self._max_buffer: int = 0  # set in full_init() once len(dataset) is known

        # ── Download COCO JSON from OSS to a local temp file ─────────────────
        # Must happen before super().__init__() calls full_init() →
        # load_data_list() → COCO(self.ann_file).
        # The returned local path starts with '/', so _join_prefix() treats it
        # as absolute and does not prepend data_root to it.
        local_ann_file = self._download_ann_file(ann_file)

        super().__init__(ann_file=local_ann_file, data_root=data_root, **kwargs)

        # Set buffer capacity after full_init() has populated data_list.
        # Formula mirrors base.py: min(ni, batch_size*8, 1000).
        # batch_size may be provided via kwargs or defaults to 16.
        _batch_size = kwargs.get("batch_size", 16)
        self._max_buffer = min(len(self), _batch_size * 8, 1000)

    # ── OSS client ───────────────────────────────────────────────────────────

    def _get_client(self) -> OssClient:
        """Return the per-process OSS client, creating it on first access."""
        import torch.utils.data

        if self._client is None:
            self._client = OssClient(
                self._endpoint, self._cred_path,
                self._config_path, self._uuid,
                cred_provider=self._cred_provider, region=self._region,
            )
            print_log(
                f"OSSDetDataset: new client [pid={os.getpid()}]",
                logger="current",
            )

        if self._client_pid is None or self._client_pid != os.getpid():
            worker_info = torch.utils.data.get_worker_info()
            if worker_info is not None:
                self._client._id    = worker_info.id
                self._client._total = worker_info.num_workers
                print_log(
                    f"OSSDetDataset: worker client "
                    f"[pid={os.getpid()}][id={self._client._id}]"
                    f"[total={self._client._total}]",
                    logger="current",
                )
            self._client_pid = os.getpid()

        return self._client

    # ── __init__ helper ───────────────────────────────────────────────────────

    def _download_ann_file(self, ann_file: str) -> str:
        """Download COCO JSON from OSS and save it to a local temp file.

        Called from ``__init__`` before ``super().__init__()``.

        Args:
            ann_file: COCO JSON path relative to data_root
                (e.g. ``'annotations/instances_train2017.json'``).

        Returns:
            Absolute local path of the downloaded file (under ``ann_cache_dir``).
        """
        client = self._get_client()

        bucket, key, local_path = get_oss_ann_path(
            self._data_root, ann_file, self._ann_cache_dir
        )
        print_log(
            f"OSSDetDataset: [pid={os.getpid()}] downloading annotation oss://{bucket}/{key}",
            logger="current",
        )

        try:
            with client.get_object(bucket, key, type=1) as file:
                buf = bytearray(4 << 20)    # 4 MiB pre-allocated buffer
                with open(local_path, "wb") as f:
                    while True:
                        n = file.readinto(buf)
                        if n <= 0:
                            break
                        f.write(buf[:n])
        except Exception as e:
            raise FileNotFoundError(
                f"OSSDetDataset: [pid={os.getpid()}] annotation not found oss://{bucket}/{key}"
            ) from e

        print_log(
            f"OSSDetDataset: [pid={os.getpid()}] annotation saved to {local_path}",
            logger="current",
        )
        return local_path

    # ── BaseDataset overrides ─────────────────────────────────────────────────

    def __deepcopy__(self, memo: dict):
        """Return ``self`` rather than a true deep copy.

        Mix augmentations (e.g. CachedMosaic) call
        ``copy.deepcopy(dataset.get_data_info(idx))`` to fetch auxiliary
        samples.  The returned ``data_info`` dict contains
        ``'oss_dataset': self``, so deepcopy would attempt to fully copy
        this object — including the C-extension OSS client, which cannot
        be pickled.

        Returning ``self`` is safe: the dataset is read-only during training
        and each worker process has its own lazily-created client instance.
        """
        memo[id(self)] = self
        return self

    def _join_prefix(self):
        """Override: mmengine's ``join_path`` / ``is_abs`` do not support
        ``oss://`` URIs (only ``s3://``, ``http://``, ``https://`` and local
        paths are recognised).  Apply a plain string join for the OSS root
        instead so that after this call:

            self.data_prefix['img']
                == 'oss://bucket/COCO/train2017/'

        ``ann_file`` is already a local ``/tmp/…`` path (absolute), so the
        parent's ``is_abs`` check passes and no joining is needed there.
        """
        base = self.data_root.rstrip('/')
        for data_key, prefix in self.data_prefix.items():
            if not isinstance(prefix, str):
                raise TypeError(
                    f'prefix should be a string, but got {type(prefix)}')
            if not os.path.isabs(prefix):
                self.data_prefix[data_key] = base + '/' + prefix.lstrip('/')
            else:
                self.data_prefix[data_key] = prefix
        # ann_file: already an absolute local path (/tmp/oss_ann_...) — no join needed.

    def get_data_info(self, idx: int) -> dict:
        """Deserialize data_info and inject the ``oss_dataset`` reference.

        Overrides :meth:`CocoDataset.get_data_info` to append
        ``'oss_dataset': self`` after deserialization.  This reference is
        consumed by :class:`OSSLoadImageFromFile` (which calls
        ``oss_dataset._get_client()`` directly) and is intentionally **not**
        stored in ``data_list`` (pickled when ``serialize_data=True``) to
        avoid serialising the OSS client and its socket state.
        """
        data_info = super().get_data_info(idx)
        data_info["oss_dataset"] = self
        return data_info

    def _evict_buffer(self) -> None:
        """Evict the oldest cached object when the buffer is full."""
        while len(self._buffered_idx) >= self._max_buffer > 0:
            old_idx = self._buffered_idx.pop(0)
            self._objects.pop(old_idx, None)
            print_log(
                f"OSSDetDataset: evict [pid={os.getpid()}]"
                f"[idx={old_idx}][buf={len(self._buffered_idx)}]",
                logger="current",
                level=logging.DEBUG,
            )

    def __getitem__(self, index: int) -> dict[str, Any]:
        print_log(
            f"OSSDetDataset: get OSS item [pid={os.getpid()}][{index}]",
            logger="current",
            level=logging.DEBUG,
        )
        return super().__getitem__(index)

    def __getitems__(self, indices: List[int]) -> List[dict[str, Any]]:
        """Batch-fetch items with OSS prefetch and idx-keyed buffer eviction.

        For each requested index:
          1. Skip if already cached in ``self._objects``.
          2. Issue a batch prefetch via ``list_objects_from_uris`` for the
             remaining (uncached) indices.
          3. Store each successfully preloaded ``DataObject`` under its idx
             in ``self._objects`` and record the idx in ``self._buffered_idx``.
          4. Apply FIFO eviction (oldest idx) whenever the buffer exceeds
             ``self._max_buffer``, mirroring ``base.py`` lines 252-257.

        ``OSSLoadImageFromFile.transform`` reads from ``self._objects[idx]``
        (injected via ``get_data_info`` as ``'sample_idx'``) and falls back
        to a live ``get_object`` call on miss.
        """
        print_log(
            f"OSSDetDataset: get OSS items [pid={os.getpid()}] {indices}",
            logger="current",
            level=logging.DEBUG,
        )
        _super = super()

        # ── Only prefetch indices that are not already cached ─────────────
        miss_indices = [i for i in indices if i not in self._objects]
        if miss_indices:
            # Single pass: resolve img_path once per miss index.
            miss_paths = [_super.get_data_info(i)["img_path"] for i in miss_indices]
            miss_objects = [new_data_object(p, 0, "") for p in miss_paths]
            # Build a key→idx reverse map so we can record hits by idx.
            key_to_idx = {p: i for p, i in zip(miss_paths, miss_indices)}
            for obj in self._get_client().list_objects_from_uris(
                miss_objects, prefetch=True, include_errors=True
            ):
                fn = "oss://" + obj.key.lstrip("/")
                idx = key_to_idx.get(fn)
                if idx is None:
                    print_log(
                        f"OSSDetDataset: prefetch key not in map "
                        f"[pid={os.getpid()}][key={obj.key}]",
                        logger="current",
                        level=logging.WARNING,
                    )
                    continue
                if obj.err() == 0 and obj.size > 0:
                    # ── Evict oldest entry before inserting a new one ─────
                    self._evict_buffer()
                    self._objects[idx] = obj.copy()
                    self._buffered_idx.append(idx)
                    print_log(
                        f"OSSDetDataset: prefetch ok "
                        f"[pid={os.getpid()}][idx={idx}][key={obj.key}]"
                        f"[size={obj.size}][buf={len(self._buffered_idx)}]",
                        logger="current",
                        level=logging.DEBUG,
                    )
                else:
                    print_log(
                        f"OSSDetDataset: prefetch failed "
                        f"[pid={os.getpid()}][idx={idx}]"
                        f"[key={obj.key}][size={obj.size}][err={obj.err()}]",
                        logger="current",
                        level=logging.WARNING,
                    )

        return [_super.__getitem__(index) for index in indices]


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

@TRANSFORMS.register_module()
class OSSLoadImageFromFile(_LoadImageFromFile):
    """OSS-aware subclass of mmcv's ``LoadImageFromFile`` for MMDetection.

    Inherits ``__init__`` from the parent, providing full support for
    ``to_float32``, ``color_type``, ``imdecode_backend``, ``ignore_empty``
    and ``backend_args``.  Overrides only ``transform()`` to fetch image
    bytes from OSS instead of the local filesystem; all decoding and
    post-processing logic is unchanged from the parent.

    Must be paired with :class:`OSSDetDataset`, which injects the
    ``'oss_dataset'`` key into every ``data_info`` dict via
    :meth:`OSSDetDataset.get_data_info`.

    Output keys (identical to ``LoadImageFromFile``):
        img        – (H, W, 3) BGR uint8 array (or float32 if to_float32=True)
        img_shape  – (H, W) tuple
        ori_shape  – (H, W) tuple
    """

    def transform(self, results: dict) -> Optional[dict]:
        oss_dataset = results.get("oss_dataset")
        if oss_dataset is None:
            raise RuntimeError(
                "OSSLoadImageFromFile requires 'oss_dataset' in results. "
                "Make sure OSSDetDataset.get_data_info() is being called."
            )
        filename = results["img_path"]
        # sample_idx is injected by BaseDataset.get_data_info() and used as
        # the key into oss_dataset._objects (the idx-keyed prefetch cache).
        sample_idx = results.get("sample_idx")
        try:
            img_bytes = b""
            im_objects = getattr(oss_dataset, "_objects", None)
            if im_objects is not None and sample_idx is not None and sample_idx in im_objects:
                obj = im_objects[sample_idx]
                obj.seek(0)
                img_bytes = obj.read()
                print_log(
                    f"OSSLoadImageFromFile: cache hit "
                    f"[pid={os.getpid()}][idx={sample_idx}][{filename}]"
                    f"[size={len(img_bytes)}]",
                    logger="current",
                    level=logging.DEBUG,
                )
            if not img_bytes:
                bucket, key = parse_oss_uri(filename)
                client      = oss_dataset._get_client()
                img_bytes   = client.get_object(bucket, key, 0, type=2).read()
                print_log(
                    f"OSSLoadImageFromFile: OSS fetch "
                    f"[pid={os.getpid()}][idx={sample_idx}][{filename}]"
                    f"[size={len(img_bytes)}]",
                    logger="current",
                    level=logging.DEBUG,
                )
            img = mmcv.imfrombytes(
                img_bytes, flag=self.color_type, backend=self.imdecode_backend)
        except Exception as e:
            print_log(
                f"OSSLoadImageFromFile: failed to load "
                f"[pid={os.getpid()}] {filename}",
                logger="current",
                level=logging.ERROR,
            )
            if self.ignore_empty:
                return None
            raise e
        assert img is not None, f"OSSLoadImageFromFile: failed to decode: {filename}"
        if self.to_float32:
            img = img.astype(np.float32)
        results["img"]       = img
        results["img_shape"] = img.shape[:2]
        results["ori_shape"] = img.shape[:2]
        return results
