# Python API

## Overview

Users can create an OssModelConnector in Python and call its provided methods to access data on OSS. The OssModelConnector provides methods for read-only access to OSS, such as list, open, and read, but does not offer any write methods for now.

## Key Features

- List and FastList

    In addition to offering a normal list implementation, a faster method called "FastList" is also provided to significantly enhance the efficiency of listing a large number of objects. FastList achieves this by concurrently sending list requests and more intelligently handling the segmentation of lists, allowing the listing of millions of objects to be completed within seconds.

- Data Prefetching

    This optimization is specifically designed for large models. After the open api is called, the ModelConnector performs high-concurrency data prefetching according to the order of opening to fully leverage the bandwidth advantages of OSS. It temporarily stores the data in memory, allowing users to quickly load data from memory when reading.

## Installation

### Requirements

- OS: Linux x86-64
- glibc: >= 2.17
- Python: 3.8-3.12
- PyTorch: >= 2.0

### Install lastest version

Download the latest OSSModelConnector package from [Release](https://github.com/aliyun/oss-connector-for-ai-ml/releases) and use pip to install it.

For example, download the `ossmodelconnector/v1.0.0rc8` for Python 3.11 and install:

```bash
wget https://github.com/aliyun/oss-connector-for-ai-ml/releases/download/ossmodelconnector%2Fv1.0.0rc1/ossmodelconnector-1.0.0rc8-cp311-cp311-manylinux_2_17_x86_64.manylinux2014_x86_64.whl

pip install ossmodelconnector-1.0.0rc8-cp311-cp311-manylinux_2_17_x86_64.manylinux2014_x86_64.whl
```

## Configuration

### Credential

When initializing the OssModelConnector, it is necessary to specify the authentication information required to access OSS.

Two methods are supported: Crendentials provider and Crendentials file.

#### Crendentials Provider

OssModelConnector supports all authentication configuration methods of the OSS Python SDK.
Please refer to the documentation:
[How to configure access credentials for OSS SDK for Python](https://www.alibabacloud.com/help/en/oss/developer-reference/python-configuration-access-credentials) /
[如何为OSS Python SDK配置访问凭证](https://help.aliyun.com/zh/oss/developer-reference/python-configuration-access-credentials)

When using it, simply pass the `credentials_provider` to the constructor of the OssModelConnector.

The following is an example of configuring authentication from environment variables.

```bash
export OSS_ACCESS_KEY_ID=<ALIBABA_CLOUD_ACCESS_KEY_ID>
export OSS_ACCESS_KEY_SECRET=<ALIBABA_CLOUD_ACCESS_KEY_SECRET>
export OSS_SESSION_TOKEN=<ALIBABA_CLOUD_SECURITY_TOKEN>
```

```python
import oss2
from oss2.credentials import EnvironmentVariableCredentialsProvider
from ossmodelconnector import OssModelConnector

connector = OssModelConnector(endpoint=ENDPOINT,
                              cred_provider=EnvironmentVariableCredentialsProvider(),
                              config_path=CONFIG_PATH)
```

The following is an example of user-custom credentials.

```python
from oss2 import CredentialsProvider
from oss2.credentials import Credentials
from ossmodelconnector import OssModelConnector

class CredentialProviderWrapper(CredentialsProvider):
    def get_credentials(self):
        return Credentials('<access_key_id>', '<access_key_secrect>')


credentials_provider = CredentialProviderWrapper()
connector = OssModelConnector(endpoint=ENDPOINT,
                              cred_provider=credentials_provider,
                              config_path=CONFIG_PATH)
```


#### Crendentials File

For now only JSON format credential file is supported.

```bash
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

```python
from ossmodelconnector import OssModelConnector

connector = OssModelConnector(endpoint=ENDPOINT,
                              cred_path='/root/.alibabacloud/credentials',
                              config_path='/tmp/config.json')
```


### Config File

The configuration file is responsible for setting parameters such as logging and concurrency. Below is an example.

```bash
mkdir -p /etc/oss-connector/
cat <<-EOF | tee /etc/oss-connector/config.json
{
    "logLevel": 1,
    "logPath": "/var/log/oss-connector/connector.log",
    "auditPath": "/var/log/oss-connector/audit.log",
    "prefetch": {
        "vcpus": 24,
        "workers": 32
    }
    "fastList": {
        "vcpus": 2,
        "workers": 16
    }
}
EOF
```

Pass the path to `config_path` when initializing OssModelConnector.

```python
import oss2
from oss2.credentials import EnvironmentVariableCredentialsProvider
from ossmodelconnector import OssModelConnector

connector = OssModelConnector(endpoint=ENDPOINT,
                              cred_provider=EnvironmentVariableCredentialsProvider(),
                              config_path='/etc/oss-connector/config.json')
```

Below is an explanation of each configuration item.

| Field         | Description                                                                                           |
|---------------|-------------------------------------------------------------------------------------------------------|
| logLevel      | The log level for log file, 0 - DEBUG, 1 - INFO, 2 - WARN, 3 - ERROR, 1 is the default value.         |
| logPath       | The path for log file, `/var/log/oss-connector/connector.log` is the default value.                   |
| auditPath     | The path for audit file, `/var/log/oss-connector/audit.log` is the default value.                     |
| prefetch.vcpus    | The vcpu number for perfetching data. 16 is the default value.                                    |
| prefetch.workers  | The worker number for perfetching data in each vcpu. 16 is the default value.                     |
| fastList.vcpus    | The vcpu number for doing fast list. 1 is the default value.                                      |
| fastList.workers  | The worker number for doing fast list in each vcpu. 16 is the default value.                      |


## Main APIs

- Initialization

    To initialize an OssModelConnector, please refer to [configuration](./configuration.md)

    ```python
    connector = OssModelConnector(endpoint=ENDPOINT,
                                  cred_provider=EnvironmentVariableCredentialsProvider(),
                                  config_path='/tmp/config.json')
    ```

- List objects

    By passing in the `bucket` and `prefix`, users can obtain a list of all objects that meet the criteria, including name and size of objects.

    ```python
    objs = connector.list('ai-testset', "geonet/images/DISC/DISC.01/2022.001")
    for obj in objs:
        print(obj.key)
        print(obj.size)
    ```

    Do FastList by passing True in the second parameter, which works more faster for large amount objects.
    The order of objects obtained by FastList is not guaranteed. If a specific order is required, users can sort the result based on `key`.

    ```python
    objs = connector.list('ai-testset', "geonet/images/DISC/DISC.01/2022.001", True)
    ```

- Open object

    Open an object through a URI. The URI format is `oss://{bucket}/{name}`. For example, `oss://ai-testset/dir1/obj1` represents an object named `dir1/obj1` in the `ai-testset` bucket.

    The open function accepts two parameters: the first is the URI, and the second is binary, which is of type bool and defaults to True, indicating that the file will be opened in binary mode. If set to False, it will be opened in text mode.

    ```python
    # open as binary mode
    obj = connector.open('oss://ai-testset/dir1/obj1')

    # open as text mode
    obj1 = connector.open('oss://ai-testset/dir1/obj1', False)
    ```

    After calling open, OssModelConnector will start prefetching in the order of the open calls. For scenarios involving loading large model files in shards (e.g. model-00001-of-00038.safetensors to model-00038-of-00038.safetensors), we recommend making sequential batch calls to open first, and then reading each one individually."

- Read object data

    Read, readinto, seek methods are provided and they follow the standard usage of Python streams.

    When a read call is made, if the data has already been prefetched into memory, it is returned directly from memory. Otherwise, a request is sent to OSS to retrieve and return the data.

    ```python
    # read whole data
    data = obj.read()

    # read a specified amount of data
    data = obj.read(4*1024*1024)

    # read into buffer
    buf = bytearray(4 * 1024 * 1024)
    obj.readinto(buf)

    # seek to a position
    obj.seek(0)
    ```

- Destroy object

    Destroying an object will release its occupied memory resources. Users can rely on Python's GC to handle it automatically, or perform manual destruction in memory-sensitive scenarios.


## Example

Below is a sample code for loading a model in multiple shards. First, open them to initiate prefetching, and then read them sequentially.

```python
import oss2
from oss2.credentials import EnvironmentVariableCredentialsProvider
from ossmodelconnector import OssModelConnector

connector = OssModelConnector(endpoint=ENDPOINT,
                              cred_provider=EnvironmentVariableCredentialsProvider(),
                              config_path='/tmp/config.json')

objs = []
for i in range(1, 39): # 1-38
    name = f"oss://ai-testset/qwen/Qwen1.5-72B-Chat/model-{i:05d}-of-00038.safetensors"
    obj = connector.open(name)
    objs.append(obj)

# using read
for i in range(0, 38): # 0-37
    while True:
        data = objs[i].read(4*1024*1024)
        if not data:
            print("read object done ", i+1)
            break

# or using readinto (recommended)
buf = bytearray(4 * 1024 * 1024)
for i in range(0, 38): # 0-37
    objs[i].seek(0)
    while True:
        n = objs[i].readinto(buf)
        if n == 0:
            print("readinto object done ", i+1)
            break
```
