"""
OSSYOLODataset — drop-in replacement for YOLODataset that loads images and
labels directly from Alibaba Cloud OSS via osstorchconnector.

Architecture (no Ultralytics source-code modification needed):

    YOLO.train()
      └─ make_oss_trainer(endpoint, cred_path, config_path)()  ← factory returns a minimal Trainer subclass
           ├─ get_dataset()                   ← parse OSS YAML, extract bucket + key prefixes
           │     data YAML: path: oss://bucket/base  train: images/train2017
           │       → data["train"] = "/bucket/base/images/train2017"  (OSS /bucket/key path)
           └─ build_dataset()
                └─ OSSYOLODataset(img_path="/bucket/base/images/train2017", oss_endpoint=..., ...)
                     ├─ __init__()            ← creates OssClient from endpoint/cred/config
                     ├─ get_img_files()       ← list objects under oss://bucket/<img_path>/
                     ├─ get_labels()          ← derive local .cache path; load or rebuild
                     │   └─ cache_labels()    ← OSS batch-download + validate labels; save .cache
                     │                           oss://bucket/.../images/.../x.jpg
                     │                             → oss://bucket/.../labels/.../x.txt
                     └─ load_image()          ← stream image bytes + cv2.imdecode

Data YAML convention (path must be an oss:// URI):
    path: oss://your-bucket/COCO_YOLO   ← oss://bucket/base_key
    train: images/train2017            ← directory  → data["train"] = "/your-bucket/COCO_YOLO/images/train2017"
    train: images/train2017.txt        ← manifest   → data["train"] = "/your-bucket/COCO_YOLO/images/train2017.txt"
    val:   images/val2017

Label path convention (mirrors Ultralytics img2label_paths):
    Image : oss://bucket/COCO_YOLO/images/train2017/000001.jpg
    Label : oss://bucket/COCO_YOLO/labels/train2017/000001.txt
    Rule  : replace the last '/images/' segment with '/labels/', swap ext → .txt

Usage:

    from osstorchconnector import make_oss_trainer
    from ultralytics import YOLO

    model = YOLO("yolov8n.pt")
    model.train(
        trainer=make_oss_trainer(
            endpoint="https://oss-cn-your-region.aliyuncs.com",
            cred_path="credentials",
            config_path="config.json",
        ),
        data="coco_oss.yaml",   # path: oss://your-bucket/COCO_YOLO
        epochs=100,
        batch=16,
        device="cpu",
    )
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any, List

import cv2
import numpy as np
import torch.utils.data

from ultralytics.data.dataset import DATASET_CACHE_VERSION, YOLODataset
from ultralytics.data.utils import (
    IMG_FORMATS,
    get_hash,
    img2label_paths,
    save_dataset_cache_file,
)
from ultralytics.models.yolo.detect.train import DetectionTrainer
from ultralytics.utils import DEFAULT_CFG, LOGGER, colorstr
from ultralytics.utils.ops import segments2boxes
from ultralytics.utils.torch_utils import unwrap_model

from .._oss_bucket_iterable import parse_oss_uri
from .._oss_client import OssClient
from .._oss_connector import new_data_object


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

class OSSYOLODataset(YOLODataset):
    """
    YOLODataset subclass that reads images and YOLO-format labels from OSS.

    Image and label paths follow the standard Ultralytics layout:
        Image : oss://bucket/COCO/images/train2017/000001.jpg
        Label : oss://bucket/COCO/labels/train2017/000001.txt
        (img2label_paths: replace '/images/' → '/labels/', swap ext → .txt)

    Extra constructor kwargs (consumed before passing remainder to parent):
        oss_endpoint    (str): OSS endpoint URL
        oss_cred_path   (str): path to credentials file (default: "")
        oss_config_path (str): path to config JSON file (default: "")
        oss_cred_provider (Any): OSS credential provider (default: None)
        oss_region      (str): OSS region (default: "")

    img_path carries the bucket as its leading component: "/bucket/prefix/..."
    (parsed by parse_oss_uri internally; no separate oss_bucket parameter needed).

    Override map:
        __init__          ultralytics/data/base.py        BaseDataset.__init__
        get_img_files     ultralytics/data/base.py        BaseDataset.get_img_files
        _parse_label_obj  ultralytics/data/utils.py       verify_image_label (logic extracted, not a method override)
        get_labels        ultralytics/data/dataset.py     YOLODataset.get_labels
        cache_labels      ultralytics/data/dataset.py     YOLODataset.cache_labels
        load_image        ultralytics/data/base.py        BaseDataset.load_image
        __getitem__       ultralytics/data/base.py        BaseDataset.__getitem__
        __getitems__      ultralytics/data/base.py        BaseDataset.__getitems__
    """

    def __init__(self, *args, **kwargs):
        # pop OSS-specific kwargs before forwarding to parent
        self._endpoint: str = kwargs.pop("oss_endpoint")
        self._cred_path: str = kwargs.pop("oss_cred_path", "")
        self._config_path: str = kwargs.pop("oss_config_path", "")
        self._cred_provider = kwargs.pop("oss_cred_provider", None)
        self._region: str = kwargs.pop("oss_region", "")
        self._uuid = uuid.uuid4()
        self._client = None
        self._client_pid = None

        super().__init__(*args, **kwargs)
        LOGGER.info(f"{self.prefix}Dataset init [pid={os.getpid()}]")

    def _get_client(self):
        if self._client is None:
            self._client = OssClient(self._endpoint, self._cred_path, self._config_path, self._uuid, cred_provider=self._cred_provider, region=self._region)
            LOGGER.info(f"{self.prefix}new client [pid={os.getpid()}]")
        if self._client_pid is None or self._client_pid != os.getpid():
            worker_info = torch.utils.data.get_worker_info()
            if worker_info is not None:
                # reset client id
                self._client._id = worker_info.id
                self._client._total = worker_info.num_workers
                LOGGER.info(f"{self.prefix}set client id [pid={os.getpid()}][id={self._client._id}][total={self._client._total}]")
            self._client_pid = os.getpid()
        return self._client

    # ------------------------------------------------------------------
    # enumerate image keys from the OSS prefix (= img_path)
    # ------------------------------------------------------------------
    def get_img_files(self, img_path: str) -> list[str]:
        """Return image OSS keys for img_path, which may be either:

        - A directory prefix  ("/bucket/COCO/images/train2017"):
            list_objects is called to enumerate all image files under it.
        - A manifest file ("/bucket/COCO/images/train2017.txt"):
            The file is downloaded and each line is resolved to an absolute
            /bucket/key path:
              - lines starting with '/' are used as-is
              - other lines (including './' prefix) are resolved relative to
                the manifest's directory (/bucket/COCO/images/<line>)

        In both cases the result is a list of /bucket/key paths.
        """
        client = self._get_client()
        bucket, key = parse_oss_uri(img_path)
        raw = []
        # Probe: is img_path a file (manifest) or a directory prefix?
        stat = client.head_object(bucket, key)
        if stat.size > 0:
            # ---- manifest file ----------------------------------------
            LOGGER.info(
                f"{self.prefix}Reading OSS manifest: "
                f"oss://{bucket}/{key}"
            )
            data = client.get_object(bucket, key, stat.size).read().decode("utf-8")
            dir_key = key.rsplit("/", 1)[0]   # directory of the manifest file

            for line in data.strip().splitlines():
                line = line.strip().lstrip("./")
                if not line:
                    continue
                if line.startswith("/"):
                    raw_key = line            # absolute /bucket/key
                else:
                    raw_key = f"/{bucket}/{dir_key}/{line}"
                if Path(raw_key).suffix[1:].lower() in IMG_FORMATS:
                    raw.append(new_data_object(raw_key, 0, ""))

        else:
            # ---- directory prefix -------------------------------------
            prefix = key.rstrip("/") + "/"
            LOGGER.info(
                f"{self.prefix}Listing OSS image objects: "
                f"oss://{bucket}/{prefix}"
            )
            for obj in self._get_client().list_objects(bucket, prefix):
                if Path(obj.key).suffix[1:].lower() in IMG_FORMATS:
                    raw.append(obj)

        # ---- common post-processing for both branches -----------------
        if not raw:
            raise FileNotFoundError(
                f"No images found in {img_path}"
            )

        raw.sort(key=lambda o: o.key)

        if self.fraction < 1.0:
            raw = raw[:max(1, round(len(raw) * self.fraction))]

        im_files = [o.key for o in raw]
        # type=0: lazy — imread will issue get_object on demand
        self.im_objects: dict = {o.key: (o, 0) for o in raw}

        LOGGER.info(f"{self.prefix}Found {len(im_files)} OSS images")
        return im_files

    # ------------------------------------------------------------------
    # derive label URIs via img2label_paths, then read from OSS.
    #    get_labels() is inherited from YOLODataset — it handles .cache
    #    load/save logic and delegates to cache_labels() below when no
    #    valid cache exists.
    #    oss://bucket/COCO/images/train2017/x.jpg
    #      → oss://bucket/COCO/labels/train2017/x.txt
    # ------------------------------------------------------------------

    def _parse_label_obj(self, oss_img_uri: str, obj, num_cls: int) -> tuple[np.ndarray, list, bool]:
        """Parse and validate a single label DataObject downloaded from OSS.

        Args:
            oss_img_uri: OSS URI of the corresponding image (for error messages).
            obj:         DataObject returned by list_objects_from_uris.
            num_cls:     Number of dataset classes (for class-index validation).

        Returns:
            (lb, segments, corrupt):
                lb       – float32 array of shape (n, 5) [cls, x, y, w, h]; empty if missing/corrupt.
                segments – list of per-instance polygon arrays (empty for box-only labels).
                corrupt  – True when the label file existed but could not be parsed.
        """
        lb = np.zeros((0, 5), dtype=np.float32)
        segments: list = []

        if obj.size == 0 or obj.err() != 0:
            return lb, segments, False  # missing → treat as background, not corrupt

        try:
            raw = [x.split() for x in obj.read().decode("utf-8").strip().splitlines() if len(x)]
            if raw:
                if any(len(x) > 6 for x in raw) and not self.use_keypoints:
                    # segment labels → derive enclosing bboxes (mirrors verify_image_label)
                    classes  = np.array([x[0] for x in raw], dtype=np.float32)
                    segments = [np.array(x[1:], dtype=np.float32).reshape(-1, 2) for x in raw]
                    lb = np.concatenate((classes.reshape(-1, 1), segments2boxes(segments)), axis=1)
                else:
                    lb = np.array(raw, dtype=np.float32)
                nl = len(lb)
                if nl:
                    assert lb.shape[1] == 5, f"labels require 5 columns, {lb.shape[1]} detected"
                    points = lb[:, 1:]
                    assert points.max() <= 1.01, (
                        f"non-normalized or out of bounds coordinates {points[points > 1.01]}"
                    )
                    assert lb.min() >= -0.01, (
                        f"negative class labels or coordinate {lb[lb < -0.01]}"
                    )
                    assert lb[:, 0].max() < num_cls, (
                        f"Label class {int(lb[:, 0].max())} exceeds dataset class count {num_cls}"
                    )
                    _, i = np.unique(lb, axis=0, return_index=True)
                    if len(i) < nl:  # duplicate rows
                        lb       = lb[i]
                        segments = [segments[x] for x in i] if segments else segments
        except Exception as e:
            LOGGER.warning(f"{self.prefix}{oss_img_uri}: ignoring corrupt label: {e}")
            return np.zeros((0, 5), dtype=np.float32), [], True

        return lb, segments, False

    def _oss_cache_path(self) -> Path:
        """Return a deterministic local .cache path derived from the first image URI.

        The parent get_labels() computes:
            cache_path = Path(self.label_files[0]).parent.with_suffix(".cache")
        which produces a garbled path for oss:// URIs.  This method derives a
        human-readable, stable path under /tmp from the directory portion of the
        first image URI, e.g.:
            oss://bucket/COCO/images/train2017/000001.jpg
              → /tmp/oss_yolo_bucket_COCO_images_train2017.cache
        """
        base = self.im_files[0].rsplit("/", 1)[0]   # drop filename, keep dir URI
        safe = base.replace("/", "_").replace(":", "").lstrip("_")
        return Path(f"/tmp/oss_yolo_{safe}.cache")

    def get_labels(self) -> list[dict]:
        """Redirect load_dataset_cache_file to the correct OSS-derived local path, then delegate to super().

        The parent hard-codes:
            cache_path = Path(self.label_files[0]).parent.with_suffix(".cache")
        and passes it to both load_dataset_cache_file() and self.cache_labels().
        We intercept load_dataset_cache_file in the dataset module so that both
        the load and the save (inside cache_labels) use _oss_cache_path() instead,
        without duplicating any parent logic.
        """
        import ultralytics.data.dataset as _ds_mod

        correct_path = self._oss_cache_path()
        _orig_load = _ds_mod.load_dataset_cache_file

        def _patched_load(_ignored_path: Path) -> dict:
            return _orig_load(correct_path)

        _ds_mod.load_dataset_cache_file = _patched_load
        try:
            return super().get_labels()
        finally:
            _ds_mod.load_dataset_cache_file = _orig_load

    def cache_labels(self, path: Path = Path("./labels.cache")) -> dict:
        """Download and validate all labels from OSS; build a cache dict compatible with
        the parent get_labels() cache format.

        Overrides YOLODataset.cache_labels() so that the inherited get_labels() can use
        the standard .cache load/save path while sourcing label data from OSS instead of
        the local filesystem.

        Args:
            path: Ignored — always replaced with _oss_cache_path() so the save location
                  matches the redirected load in get_labels().

        Returns:
            Cache dict with keys: 'labels', 'hash', 'results', 'msgs'.
        """
        path = self._oss_cache_path()
        self.label_files = img2label_paths(self.im_files)
        LOGGER.info(
            f"{self.prefix}Getting OSS label objects: "
            f"oss:/{self.label_files[0].rsplit('/', 1)[0]} ..."
        )

        num_cls = len(self.data["names"])
        x: dict = {"labels": []}
        nf, nm, ne, nc, msgs = 0, 0, 0, 0, []  # found, missing, empty, corrupt, messages

        for oss_img_uri, obj in zip(
            self.im_files,
            self._get_client().list_objects_from_uris(
                [new_data_object(uri, 0, "") for uri in self.label_files],
                prefetch=True, include_errors=True,
            ),
        ):
            missing = obj.size == 0 or obj.err() != 0
            lb, segments, corrupt = self._parse_label_obj(oss_img_uri, obj, num_cls)

            if corrupt:
                nc += 1
                msgs.append(f"{self.prefix}{oss_img_uri}: corrupt label ignored")
            elif missing:
                nm += 1  # background image — still added to labels below
            elif len(lb) == 0:
                ne += 1  # empty label file
                nf += 1
            else:
                nf += 1

            x["labels"].append({
                "im_file":     oss_img_uri,
                "shape":       (0, 0),   # NOTE: OSS does not pre-fetch image shape; rect=True unsupported
                "cls":         lb[:, 0:1],   # n, 1
                "bboxes":      lb[:, 1:],    # n, 4
                "segments":    segments,
                "keypoints":   None,
                "normalized":  True,
                "bbox_format": "xywh",
            })

        if msgs:
            LOGGER.info("\n".join(msgs))
        if nf == 0:
            LOGGER.warning(f"{self.prefix}No labels found in OSS. Training may not work correctly.")

        x["hash"]    = get_hash(self.label_files + self.im_files)
        x["results"] = nf, nm, ne, nc, len(self.im_files)
        x["msgs"]    = msgs
        save_dataset_cache_file(self.prefix, path, x, DATASET_CACHE_VERSION)
        return x

    # ------------------------------------------------------------------
    # stream image bytes from OSS → cv2.imdecode
    # ------------------------------------------------------------------
    def imread(self, f: str, flags: int = cv2.IMREAD_COLOR) -> np.ndarray | None:
        """Read image by OSS key f.

        type=1 (preloaded via list_objects_from_uris): read directly from the in-memory DataObject.
        type=0 (lazy via list_objects): issue a fresh get_object GET to OSS.
        """
        obj, typ = self.im_objects[f]
        if typ == 1:  # preloaded — data already in memory, read directly
            obj.seek(0)
            data = obj.read()
            LOGGER.debug(f"{self.prefix}read from preloaded [{f}]")
        else:          # lazy — fetch from OSS on demand
            bucket, k = parse_oss_uri(f)
            data = self._get_client().get_object(bucket, k, obj.size).read()
            LOGGER.debug(f"{self.prefix}read from OSS [{f}]")
        return cv2.imdecode(np.frombuffer(data, np.uint8), flags)

    def load_image(self, i: int, rect_mode: bool = True) -> tuple[np.ndarray, tuple[int, int], tuple[int, int]]:
        """Load image i, temporarily redirecting base.imread to self.imread for OSS-aware dispatch."""
        import ultralytics.data.base as _base
        _orig = _base.imread
        _base.imread = self.imread
        try:
            return super().load_image(i, rect_mode)
        finally:
            _base.imread = _orig

    def __getitem__(self, index: int) -> dict[str, Any]:
        LOGGER.debug(f"{self.prefix}Getting OSS item [{index}]: {self.im_files[index]}")
        return super().__getitem__(index)

    def __getitems__(self, indices: List[int]) -> List[dict[str, Any]]:
        LOGGER.debug(f"{self.prefix}Getting OSS items [{os.getpid()}][{indices}]")
        # skip indices whose images are already held in RAM cache
        to_fetch = [i for i in indices if self.ims[i] is None]
        if to_fetch:
            keys = [self.im_files[i] for i in to_fetch]
            originals = {k: self.im_objects[k] for k in keys}
            # pass original DataObject descriptors directly — no new_data_object wrapper needed
            for key, obj in zip(
                keys,
                self._get_client().list_objects_from_uris(
                    [src for (src, _) in originals.values()], prefetch=True, include_errors=True,
                ),
            ):
                self.im_objects[key] = (obj.copy(), 1)  # mark preloaded, need copy
            results = [self.__getitem__(index) for index in indices]
            self.im_objects.update(originals)    # restore to lazy type-0
        else:
            results = [self.__getitem__(index) for index in indices]
        return results


# ---------------------------------------------------------------------------
# Trainer factory
# ---------------------------------------------------------------------------

def _parse_oss_yaml(yaml_path: str) -> dict:
    """Parse an OSS data YAML and return data_dict with /bucket/key paths.

    The YAML must have 'path: oss://bucket/base_key'.  train/val values are
    joined with bucket + base_key to produce /bucket/key paths stored back
    into the data dict.

    Example YAML:
        path: oss://your-bucket/COCO_YOLO
        train: images/train2017   → data["train"] = "/your-bucket/COCO_YOLO/images/train2017"
        val:   images/val2017     → data["val"]   = "/your-bucket/COCO_YOLO/images/val2017"
    """
    from ultralytics.nn.autobackend import check_class_names
    from ultralytics.utils import YAML as _YAML

    data = _YAML.load(yaml_path)
    path = str(data.get("path", "")).rstrip("/")
    if not path.startswith("oss://"):
        raise ValueError(
            f"OSS trainer requires 'path: oss://bucket/...' in the data YAML, "
            f"got: {path!r}"
        )
    # oss://bucket/base_key → bucket="your-bucket", base_key="COCO_YOLO"
    rest = path[len("oss://"):]
    bucket, _, base_key = rest.partition("/")

    for k in ("train", "val", "test", "minival"):
        if data.get(k):
            suffix = str(data[k]).lstrip("/")
            # "/bucket" + "/" + "COCO_YOLO/images/train2017" → "/bucket/COCO_YOLO/images/train2017"
            data[k] = "/" + bucket + "/" + (base_key.rstrip("/") + "/" + suffix).lstrip("/")

    # Normalise names / nc (mirrors check_det_dataset)
    if "names" not in data and "nc" not in data:
        raise SyntaxError(f"{yaml_path}: 'names' or 'nc' key missing")
    if "names" not in data:
        data["names"] = {i: f"class_{i}" for i in range(data["nc"])}
    data["nc"] = len(data["names"])
    data["names"] = check_class_names(data["names"])
    data["channels"] = data.get("channels", 3)
    data["yaml_file"] = str(yaml_path)

    return data


def make_oss_trainer(
    endpoint: str,
    cred_path: str = "",
    config_path: str = "",
    cred_provider: Any = None,
    region: str = "",
) -> type[DetectionTrainer]:
    """Return a minimal DetectionTrainer subclass that reads data from OSS.

    Bucket and key prefixes are taken from the data YAML (no external params):
        path: oss://bucket/base_key   →  bucket extracted here
        train: images/train2017       →  data["train"] = "base_key/images/train2017"

    OssClient is created inside each OSSYOLODataset instance; the trainer
    itself holds only the connection parameters.

    Args:
        endpoint:    OSS endpoint URL.
        cred_path:   Path to credentials file (default: "").
        config_path: Path to config JSON file (default: "").
        cred_provider: OSS credential provider (default: None).
        region:      OSS region (default: "").

    Returns:
        A Trainer class (not an instance) ready to be passed to model.train(trainer=...).
    """
    _endpoint      = endpoint
    _cred_path     = cred_path
    _config_path   = config_path
    _cred_provider = cred_provider
    _region        = region

    class _OSSDetectionTrainer(DetectionTrainer):
        """Auto-generated DetectionTrainer that reads images/labels from OSS."""

        def __init__(self, cfg=DEFAULT_CFG, overrides=None, _callbacks=None):
            super().__init__(cfg=cfg, overrides=overrides, _callbacks=_callbacks)
            # Ultralytics forces workers=0 on CPU (trainer.py L160); restore a
            # sensible default so OSS prefetch workers are actually spawned.
            if self.device.type == "cpu" and self.args.workers == 0:
                self.args.workers = 1
                LOGGER.info(
                    f"OSS trainer: restored workers={self.args.workers} "
                    f"(Ultralytics forces workers=0 on CPU; overridden for OSS prefetch)"
                )
            # Validate OSS credentials are accessible
            if _cred_path and not Path(_cred_path).exists():
                raise FileNotFoundError(f"OSS credentials not found: {_cred_path}")
            if _config_path and not Path(_config_path).exists():
                raise FileNotFoundError(f"OSS config not found: {_config_path}")
            LOGGER.info(
                f"OSS trainer: endpoint={_endpoint}  "
                f"cred={_cred_path}  config={_config_path}  "
                f"workers={self.args.workers}"
            )

        def get_dataset(self):
            """Parse the OSS data YAML and build data dict with /bucket/key paths.

            Overrides BaseTrainer.get_dataset() to bypass check_det_dataset(),
            which would resolve YAML paths as local filesystem paths.
            """
            data = _parse_oss_yaml(self.args.data)
            if self.args.single_cls:
                LOGGER.info("Overriding class names with single class.")
                data["names"] = {0: "item"}
                data["nc"] = 1
            return data

        def build_dataset(self, img_path: str, mode: str = "train", batch: int | None = None):
            """Return OSSYOLODataset for the given mode (train or val).

            img_path is data["train"] or data["val"] set by get_dataset(),
            i.e. a /bucket/key path (e.g. "/your-bucket/COCO_YOLO/images/train2017").
            """
            gs = max(int(unwrap_model(self.model).stride.max()), 32)
            return OSSYOLODataset(
                img_path=img_path,
                imgsz=self.args.imgsz,
                batch_size=batch,
                augment=mode == "train",
                hyp=self.args,
                rect=self.args.rect or (mode == "val"),
                cache=self.args.cache or None,
                single_cls=self.args.single_cls or False,
                stride=gs,
                pad=0.0 if mode == "train" else 0.5,
                prefix=colorstr(f"{mode}: "),
                task=self.args.task,
                classes=self.args.classes,
                data=self.data,
                fraction=self.args.fraction if mode == "train" else 1.0,
                oss_endpoint=_endpoint,
                oss_cred_path=_cred_path,
                oss_config_path=_config_path,
                oss_cred_provider=_cred_provider,
                oss_region=_region,
            )

        def final_eval(self):
            """Override to bypass check_det_dataset() during final validation.

            The stock final_eval() calls validator(model=model) without a trainer,
            which triggers the validator's else-branch (validator.py L182-183):
                self.data = check_det_dataset(self.args.data)
            This always overwrites self.data and fails for oss:// paths.

            Fix: temporarily replace check_det_dataset in the validator module
            with a lambda that returns the already-parsed OSS data dict, then
            restore it after the call.
            """
            import ultralytics.engine.validator as _val_mod
            _orig_check = _val_mod.check_det_dataset
            _preloaded  = self.data  # parsed by get_dataset() → _parse_oss_yaml()
            _val_mod.check_det_dataset = lambda *a, **kw: _preloaded
            try:
                super().final_eval()
            finally:
                _val_mod.check_det_dataset = _orig_check

    return _OSSDetectionTrainer
