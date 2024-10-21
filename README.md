# OSS Connector for AI/ML

## Overview

The OSS Connector for AI/ML is a high-performance Python library specifically designed for AI and ML scenariosis, tailored to work with Alibaba Cloud OSS (Object Storage Service).

OSS Connector for AI/ML provides both [Map-style and Iterable-style datasets](https://pytorch.org/docs/stable/data.html#dataset-types) for loading datasets from OSS.
And also provides a method for loading and saving checkpoints from and to OSS.

The core part of is OSS Connector for AI/ML is implemented in C++ using [PhotonLibOS](https://github.com/alibaba/PhotonLibOS). This repository only contains the code of Python.


## Requirements

- OS: Linux x86-64
- glibc: >= 2.17
- Python: 3.8-3.12
- PyTorch: >= 2.0

## Installation

```shell
pip install osstorchconnector
```

## Configuration

### Credential

For now only JSON format credential file is supported.
```shell
mkdir -p /root/.alibabacloud/
cat <<-EOF | tee /root/.alibabacloud/credentials
{
    "AccessKeyId": "<Access-key-id>",
    "AccessKeySecret": "<Access-key-secret>",
    "SecurityToken": "<Security-Token>",
    "Expiration": "2024-08-02T15:04:05Z"
}
EOF
```
`SecurityToken` and  `Expiration` are optional.
The credential file must be updated before expiration to avoid authorization errors.
In the future, configuring credentials using the aliyun-oss-python-sdk will be supported.

### Config

```bash
mkdir -p /etc/oss-connector/
cat <<-EOF | tee /etc/oss-connector/config.json
{
    "logLevel": 1,
    "logPath": "/var/log/oss-connector/connector.log",
    "auditPath": "/var/log/oss-connector/audit.log",
    "datasetConfig": {
        "prefetchConcurrency": 24,
        "prefetchWorker": 2
    },
    "checkpointConfig": {
        "prefetchConcurrency": 24,
        "prefetchWorker": 4,
        "uploadConcurrency": 64
    }
}
EOF
```
| Field         | Description                                                                                           |
|---------------|-------------------------------------------------------------------------------------------------------|
| logLevel      | The log level for log file, 0 - DEBUG, 1 - INFO, 2 - WARN, 3 - ERROR                                  |
| logPath       | The path for log file, `/var/log/oss-connector/connector.log` is the default value.                   |
| auditPath     | The path for audit file, `/var/log/oss-connector/audit.log` is the default value.                     |
| datasetConfig.prefetchConcurrency    | The concurrency for perfetching data from Dataset. 24 is the default value.    |
| datasetConfig.prefetchWorker         | The vcpu number for perfetching data from Dataset. 2 is the default value.     |
| checkpointConfig.prefetchConcurrency | The concurrency for perfetching checkpoint . 24 is the default value.          |
| checkpointConfig.prefetchWorker      | The vcpu number for perfetching checkpoint. 4 is the default value.            |
| checkpointConfig.uploadConcurrency   | The concurrency for uploading checkpoint. 64 is the default value.             |


## Examples

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

OssIterableDataset includes prefetch optimization. When the DataLoader is configured with multiple workers, the iteration order may not be deterministic (local order might be disrupted).

### Checkpoint

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

## Related

[OSS Connector for AI/ML 中文文档](https://help.aliyun.com/zh/oss/developer-reference/oss-connector-for-ai-ml)

## License

This project is licensed under the terms of the [MIT License](LICENSE).