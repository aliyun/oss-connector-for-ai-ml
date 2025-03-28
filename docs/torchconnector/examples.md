# Examples

## Dataset

### IterableDataset

```py
from osstorchconnector import OssIterableDataset

ENDPOINT = "http://oss-cn-beijing-internal.aliyuncs.com"
CONFIG_PATH = "/etc/oss-connector/config.json"
CRED_PATH = "/root/.alibabacloud/credentials"
OSS_URI = "oss://ossconnectorbucket/EnglistImg/Img/BadImag/Bmp/Sample001/"

# 1) from_prefix
iterable_dataset = OssIterableDataset.from_prefix(OSS_URI, endpoint=ENDPOINT, cred_path=CRED_PATH, config_path=CONFIG_PATH)
for item in iterable_dataset:
    print(item.key)
    print(item.size)
    content = item.read()
    print(len(content))
    item.close()


# 2) from_objects
uris = [
    "oss://ossconnectorbucket/EnglistImg/Img/BadImag/Bmp/Sample001/img001-00001.png",
    "oss://ossconnectorbucket/EnglistImg/Img/BadImag/Bmp/Sample001/img001-00002.png",
    "oss://ossconnectorbucket/EnglistImg/Img/BadImag/Bmp/Sample001/img001-00003.png"
]

iterable_dataset = OssIterableDataset.from_objects(uris, endpoint=ENDPOINT, cred_path=CRED_PATH, config_path=CONFIG_PATH)]
for item in iterable_dataset:
    print(item.key)
    print(item.size)
    content = item.read()
    print(len(content))
    item.close()
```

### MapDataset

```py
from osstorchconnector import OssMapDataset

ENDPOINT = "http://oss-cn-beijing-internal.aliyuncs.com"
CONFIG_PATH = "/etc/oss-connector/config.json"
CRED_PATH = "/root/.alibabacloud/credentials"
OSS_URI = "oss://ossconnectorbucket/EnglistImg/Img/BadImag/Bmp/Sample001/"

# 1) from_prefix
map_dataset = OssMapDataset.from_prefix(OSS_URI, endpoint=ENDPOINT, cred_path=CRED_PATH, config_path=CONFIG_PATH)
# random access
item = map_dataset[0]
print(item.key)
content = item.read()
print(item.size)
print(len(content))
item.close()

# or
with map_dataset[5] as item:
    print(item.key)
    content = item.read()
    print(item.size)
    print(len(content))

# iterable
for item in map_dataset:
    print(item.key)
    print(item.size)
    content = item.read()
    print(len(content))
    item.close()


# 2) from_objects
uris = [
    "oss://ossconnectorbucket/EnglistImg/Img/BadImag/Bmp/Sample001/img001-00001.png",
    "oss://ossconnectorbucket/EnglistImg/Img/BadImag/Bmp/Sample001/img001-00002.png",
    "oss://ossconnectorbucket/EnglistImg/Img/BadImag/Bmp/Sample001/img001-00003.png"
]

map_dataset = OssMapDataset.from_objects(uris, endpoint=ENDPOINT, cred_path=CRED_PATH, config_path=CONFIG_PATH)
# random access
item = map_dataset[1]
print(item.key)
print(item.size)
content = item.read()
print(len(content))
item.close()

# iterable
for item in map_dataset:
    print(item.key)
    print(item.size)
    content = item.read()
    print(len(content))
    item.close()
```

Please note that OssMapDataset performs an OSS list objects operation under the given prefix first (which may take some time).

### Manifest file

Manifest file contains objects name (and label) of OSS objects.
Building datasets with manifest file can reduce the overhead of listing objects in OSS, making it suitable for datasets with a large number of objects and repeated dataset loading.

A manifest file must be constructed in advance, and a method for parsing it must be provided during use.
Below are examples of manifest files and loading a dataset with manifest file.

Example manifest file with object name:
```
Img/BadImag/Bmp/Sample001/img001-00001.png
Img/BadImag/Bmp/Sample001/img001-00002.png
Img/BadImag/Bmp/Sample001/img001-00003.png
```

Example manifest file with object name and label:
```
Img/BadImag/Bmp/Sample001/img001-00001.png label1
Img/BadImag/Bmp/Sample001/img001-00002.png label2
Img/BadImag/Bmp/Sample001/img001-00003.png label3
```

```py
from osstorchconnector import OssIterableDataset

ENDPOINT = "http://oss-cn-beijing-internal.aliyuncs.com"
CONFIG_PATH = "/etc/oss-connector/config.json"
CRED_PATH = "/root/.alibabacloud/credentials"
OSS_URI = "oss://ossconnectorbucket/EnglistImg/Img/BadImag/Bmp/Sample001/"

# manifest_parser
def manifest_parser(reader: io.IOBase) -> Iterable[Tuple[str, str]]:
    lines = reader.read().decode("utf-8").strip().split("\n")
    for i, line in enumerate(lines):
        try:
            items = line.strip().split(' ')
            if len(items) >= 2:
                key = items[0]
                label = items[1]
                yield (key, label)
            elif len(items) == 1:
                key = items[0]
                yield (key, '')
            else:
                raise ValueError("format error")
        except ValueError as e:
            raise e

# from local manifest_file
iterable_dataset = OssIterableDataset.from_manifest_file("manifest_file", manifest_parser, "oss://ossconnectorbucket/EnglistImg/", endpoint=ENDPOINT, cred_path=CRED_PATH, config_path=CONFIG_PATH)
for item in iterable_dataset:
    print(item.key)
    print(item.size)
    print(item.label)
    content = item.read()
    print(len(content))
    item.close()

# manifest_file on oss
iterable_dataset = OssIterableDataset.from_manifest_file("oss://ossconnectorbucket/manifest_file/EnglistImg/manifest_file", manifest_parser, "oss://ossconnectorbucket/EnglistImg/", endpoint=ENDPOINT, cred_path=CRED_PATH, config_path=CONFIG_PATH)
```

### Dataset and transform

```py
import sys
import io
import torchvision.transforms as transforms
from PIL import Image

from osstorchconnector import OssIterableDataset, OssMapDataset

ENDPOINT = "http://oss-cn-beijing-internal.aliyuncs.com"
CONFIG_PATH = "/etc/oss-connector/config.json"
CRED_PATH = "/root/.alibabacloud/credentials"
OSS_URI = "oss://ossconnectorbucket/EnglistImg/Img/BadImag/Bmp/Sample001/"

trans = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
])

def transform(data):
    try:
        img = Image.open(io.BytesIO(data.read())).convert('RGB')
        val = trans(img)
    except Exception as e:
        raise e
    return val, data.label

iterable_dataset = OssIterableDataset.from_prefix(OSS_URI, endpoint=ENDPOINT, transform=transform, cred_path=CRED_PATH, config_path=CONFIG_PATH)

for item in iterable_dataset:
    print(item[0])
    print(item[1])
```

### Pytorch dataloader
```py
import sys
import io
import torch
import torchvision.transforms as transforms
from PIL import Image
from osstorchconnector import OssIterableDataset, OssMapDataset

ENDPOINT = "http://oss-cn-beijing-internal.aliyuncs.com"
CONFIG_PATH = "/etc/oss-connector/config.json"
CRED_PATH = "/root/.alibabacloud/credentials"
OSS_URI = "oss://ossconnectorbucket/EnglistImg/Img/BadImag/Bmp/Sample001/"


trans = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
])

def transform(data):
    try:
        img = Image.open(io.BytesIO(data.read())).convert('RGB')
        val = trans(img)
    except Exception as e:
        raise e
    return val, data.key, data.label

# OssIterableDataset
iterable_dataset = OssIterableDataset.from_prefix(OSS_URI, endpoint=ENDPOINT, transform=transform, cred_path=CRED_PATH, config_path=CONFIG_PATH)
loader = torch.utils.data.DataLoader(iterable_dataset, batch_size=256, num_workers=32, prefetch_factor=2)
for i, (datas, keys, labels) in enumerate(loader):
    print(datas)
    print(keys)

# OssMapDataset with shuffle
map_dataset = OssMapDataset.from_prefix(OSS_URI, endpoint=ENDPOINT, transform=transform, cred_path=CRED_PATH, config_path=CONFIG_PATH)
loader = torch.utils.data.DataLoader(map_dataset, batch_size=256, num_workers=32, prefetch_factor=2, shuffle=True)
for i, (datas, keys, labels) in enumerate(loader):
    print(datas)
    print(keys)
```

When using with DataLoader, the main DataLoader worker responsible for listing from OSS or receiving objects from_prefix/from_manifest_file, all workers obtain their assigned objects from the main worker.
This approach avoids issues of redundant listing and data reading (which may exist in other connectors), allowing better performance from multiple workers. When testing data download speed (excluding transform and other CPU-bound workload) with a large number of small files (e.g., ImageNet), it can exceed 10GB/s.

OssIterableDataset includes prefetch optimization by increasing concurrency. When the DataLoader is configured with multiple workers, the iteration order may not be deterministic (local order might be disrupted).

## Checkpoint

```py
import torch
from osstorchconnector import OssCheckpoint

ENDPOINT = "http://oss-cn-beijing-internal.aliyuncs.com"
CONFIG_PATH = "/etc/oss-connector/config.json"
CRED_PATH = "/root/.alibabacloud/credentials"

checkpoint = OssCheckpoint(endpoint=ENDPOINT, cred_path=CRED_PATH, config_path=CONFIG_PATH)

# read checkpoint
CHECKPOINT_READ_URI = "oss://ossconnectorbucket/checkpoint/epoch.0"
with checkpoint.reader(CHECKPOINT_READ_URI) as reader:
   state_dict = torch.load(reader)

# write checkpoint
CHECKPOINT_WRITE_URI = "oss://ossconnectorbucket/checkpoint/epoch.1"
with checkpoint.writer(CHECKPOINT_WRITE_URI) as writer:
   torch.save(state_dict, writer)
```

OssCheckpoint can be used for checkpoints, and also for high-speed uploading and downloading of arbitrary objects. In our testing environment, the download speed can exceed 15GB/s.