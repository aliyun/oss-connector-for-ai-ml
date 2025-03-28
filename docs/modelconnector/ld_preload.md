# Loading Models via LD_PRELOAD

## Overview
In multi-process scenarios, the OSSModelConnector configuration initialized via the Python interface may be lost in Python sub-processes, causing OSS data to fail to load. For example, `vllm.entrypoints.openai.api_server`, where the main process is the API server and model inference happens in sub-processes; or in multi-GPU scenarios, where different processes load models onto different GPUs.

In such cases, you can start the OSSModelConnector using the `LD_PRELOAD` method, passing configuration parameters via environment variables. Compared to initializing with Python, this `LD_PRELOAD` method generally does not require code modifications.

## Installation

Download the installation package `oss-connector-lib` from [Release](https://github.com/aliyun/oss-connector-for-ai-ml/releases)

For example, download the `oss-connector-lib-1.0.0rc8` and install.

rpm:

```shell
yum install -y https://github.com/aliyun/oss-connector-for-ai-ml/releases/download/ossmodelconnector%2Fv1.0.0rc8/oss-connector-lib-1.0.0rc8.x86_64.rpm
```

deb:
```shell
wget https://github.com/aliyun/oss-connector-for-ai-ml/releases/download/ossmodelconnector%2Fv1.0.0rc8/oss-connector-lib-1.0.0rc8.x86_64.deb
dpkg -i oss-connector-lib-1.0.0rc8.x86_64.deb
```

**After installation, check `/usr/local/lib/libossc_preload.so`.**


## Usage Method

### Configuration File

The configuration file path is `/etc/oss-connector/config.json`. The installation package **already includes** a default configuration file as follows:

```json
{
    "logLevel": 1,
    "logPath": "/var/log/oss-connector/connector.log",
    "auditPath": "/var/log/oss-connector/audit.log",
    "prefetch": {
        "vcpus": 16,
        "workers": 16
    }
}
```

The main performance-related parameters are:

- `prefetch.vcpus`: Number of vCPUs (CPU cores) to prefetch, default value is 16.
- `prefetch.workers`: Number of coroutines per prefetched vCPU, default value is 16.

### Configure Environment Variables

| Environment Variable KEY | Environment Variable VALUE Description |
| --- | --- |
| OSS_ACCESS_KEY_ID | OSS access key |
| OSS_ACCESS_KEY_SECRET | OSS access key secret |
| OSS_SESSION_TOKEN | Optional, STS token |
| OSS_ENDPOINT | Endpoint for OSS, e.g., `http://oss-cn-beijing-internal.aliyuncs.com`, default HTTP schema is `http` |
| OSS_PATH | OSS model directory, e.g., `oss://example-bucket/example-model-path/` |
| MODEL_DIR | Local model directory, passed to vLLM or other inference frameworks. To avoid interference from dirty data, it is recommended to clear this directory first. Temporary data will be downloaded during use, and it can be deleted afterward. |
| LD_PRELOAD | `/usr/local/lib/libossc_preload.so` |
| **ENABLE_CONNECTOR** | `1`, **Enable Connector, must be set for the main process** |

### Start Python Program

```shell
LD_PRELOAD=/usr/local/lib/libossc_preload.so ENABLE_CONNECTOR=1 OSS_ACCESS_KEY_ID=${akid} OSS_ACCESS_KEY_SECRET=${aksecret} OSS_ENDPOINT=${endpoint} OSS_PATH=oss://${bucket}/${path}/ MODEL_DIR=/tmp/model python3 -m vllm.entrypoints.openai.api_server --model /tmp/model --trust-remote-code --tensor-parallel-size 1 --disable-custom-all-reduce
```

### Note!

1. `MODEL_DIR` must be consistent with the model dir for AI framework, e.g., vLLM's `--model`.

2. `ENABLE_CONNECTOR=1` must be set for the entrypoint process. `LD_PRELOAD` is recommended to be set for the entrypoint process but can also be directly set for the container.

3. Currently, when starting the OSSModelConnector via `LD_PRELOAD`, additional memory used for caching will be released with a delay, currently set at 120 seconds.

4. If using `nohup` to start, do not configure the environment variables for `nohup`. Instead, encapsulate the environment variables and startup command into a script and execute `nohup` on the script.

5. For now, try to use this method in single-machine scenarios. In multi-machine setups, there might be repeated loading or other unknown issues.
