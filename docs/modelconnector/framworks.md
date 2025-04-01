# Work with AI frameworks

## Overview

Mainstream AI inference frameworks, such as vllm and transformers, load models from a local directory. The number of files in the model directory is not large, comprising several small files and multiple larger model files. For example, the directory below shows the model directory for Qwen2.5-72B, including 37 large safetensors files and several small files.

```bash
# ll -lh /root/Qwen2.5-72B
total 136G
-rw-r--r-- 1 root root  664 Sep 25 12:23 config.json
-rw-r--r-- 1 root root    2 Sep 25 12:23 configuration.json
-rw-r--r-- 1 root root  138 Sep 25 12:23 generation_config.json
-rw-r--r-- 1 root root 6.8K Sep 25 12:23 LICENSE
-rw-r--r-- 1 root root 1.6M Sep 25 12:23 merges.txt
-rw-r--r-- 1 root root 3.6G Sep 25 12:28 model-00001-of-00037.safetensors
-rw-r--r-- 1 root root 3.8G Sep 25 12:33 model-00002-of-00037.safetensors
-rw-r--r-- 1 root root 3.6G Sep 25 12:39 model-00003-of-00037.safetensors
-rw-r--r-- 1 root root 3.8G Sep 25 12:44 model-00004-of-00037.safetensors
-rw-r--r-- 1 root root 3.8G Sep 25 12:50 model-00005-of-00037.safetensors
-rw-r--r-- 1 root root 3.8G Sep 25 12:55 model-00006-of-00037.safetensors
-rw-r--r-- 1 root root 3.6G Sep 25 13:00 model-00007-of-00037.safetensors
-rw-r--r-- 1 root root 3.8G Sep 25 13:06 model-00008-of-00037.safetensors
-rw-r--r-- 1 root root 3.8G Sep 25 13:11 model-00009-of-00037.safetensors
-rw-r--r-- 1 root root 3.8G Sep 25 13:17 model-00010-of-00037.safetensors
-rw-r--r-- 1 root root 3.6G Sep 25 13:22 model-00011-of-00037.safetensors
-rw-r--r-- 1 root root 3.8G Sep 25 13:28 model-00012-of-00037.safetensors
-rw-r--r-- 1 root root 3.8G Sep 25 13:33 model-00013-of-00037.safetensors
-rw-r--r-- 1 root root 3.8G Sep 25 13:39 model-00014-of-00037.safetensors
-rw-r--r-- 1 root root 3.6G Sep 25 13:44 model-00015-of-00037.safetensors
-rw-r--r-- 1 root root 3.8G Sep 25 13:49 model-00016-of-00037.safetensors
-rw-r--r-- 1 root root 3.8G Sep 25 13:55 model-00017-of-00037.safetensors
-rw-r--r-- 1 root root 3.8G Sep 25 14:00 model-00018-of-00037.safetensors
-rw-r--r-- 1 root root 3.6G Sep 25 14:06 model-00019-of-00037.safetensors
-rw-r--r-- 1 root root 3.8G Sep 25 14:11 model-00020-of-00037.safetensors
-rw-r--r-- 1 root root 3.8G Sep 25 14:17 model-00021-of-00037.safetensors
-rw-r--r-- 1 root root 3.8G Sep 25 14:22 model-00022-of-00037.safetensors
-rw-r--r-- 1 root root 3.6G Sep 25 14:27 model-00023-of-00037.safetensors
-rw-r--r-- 1 root root 3.8G Sep 25 14:33 model-00024-of-00037.safetensors
-rw-r--r-- 1 root root 3.8G Sep 25 14:38 model-00025-of-00037.safetensors
-rw-r--r-- 1 root root 3.8G Sep 25 14:44 model-00026-of-00037.safetensors
-rw-r--r-- 1 root root 3.6G Sep 25 14:49 model-00027-of-00037.safetensors
-rw-r--r-- 1 root root 3.8G Sep 25 14:55 model-00028-of-00037.safetensors
-rw-r--r-- 1 root root 3.8G Sep 25 15:00 model-00029-of-00037.safetensors
-rw-r--r-- 1 root root 3.8G Sep 25 15:05 model-00030-of-00037.safetensors
-rw-r--r-- 1 root root 3.6G Sep 25 15:11 model-00031-of-00037.safetensors
-rw-r--r-- 1 root root 3.8G Sep 25 15:16 model-00032-of-00037.safetensors
-rw-r--r-- 1 root root 3.8G Sep 25 15:22 model-00033-of-00037.safetensors
-rw-r--r-- 1 root root 3.8G Sep 25 15:27 model-00034-of-00037.safetensors
-rw-r--r-- 1 root root 3.6G Sep 25 15:32 model-00035-of-00037.safetensors
-rw-r--r-- 1 root root 3.8G Sep 25 15:38 model-00036-of-00037.safetensors
-rw-r--r-- 1 root root 3.3G Sep 25 15:43 model-00037-of-00037.safetensors
-rw-r--r-- 1 root root  78K Sep 25 15:43 model.safetensors.index.json
-rw-r--r-- 1 root root 3.8K Sep 25 15:43 README.md
-rw-r--r-- 1 root root 7.1K Sep 25 15:43 tokenizer_config.json
-rw-r--r-- 1 root root 6.8M Sep 25 15:43 tokenizer.json
-rw-r--r-- 1 root root 2.7M Sep 25 15:43 vocab.json
```

Another common scenario is like the Stable Diffusion web UI, where a large number of models are stored in one or several folders, and there might be situations where models need to be switched during use.

The OssModelConnector offers a method to directly pass in an OSS directory to the inference frameworks and read the models directly from OSS.

Compared to the FUSE-based mounting solution, OssModelConnector has a significant performance advantage. Compared to downloading before loading to framworks, the OssModelConnector allows for simultaneous downloading and loading, achieving faster model deployment speeds.

## Usage

Before starting inference frameworks like vllm and transformers, call `connector.prepare_directory(oss_dir, model_dir)`, and then pass model_dir to the inference framework.

The `oss_dir` is the directory in OSS where the model files are stored, formatted as a URL, for example, `oss://ai-testset/qwen/qwen2.5-72B/`.

The `model_dir` is the local model directory. During the process, the connector will download some temporary data into model_dir, which can be deleted afterward.

After the prepare_directory called, the OssModelConnector begins downloading and prefetching data. Smaller files will be downloaded to the `model_dir` concurrently, while larger model files start prefetching into memory in alphabetical order. To avoid being corrupted by dirty data, the OssModelConnector will clean the contents of the `model_dir` before running.

## Examples

### Transformers
```python
from transformers import AutoModelForCausalLM, AutoTokenizer
from ossmodelconnector import OssModelConnector

# initialize OssModelConnector
connector = OssModelConnector(...)

# prepare_directory
oss_path = "oss://ai-testset/qwen/Qwen25-75B"
model_dir = '/root/abc/'
connector.prepare_directory(oss_path, model_dir)

# pass model_dir to transformer
tokenizer = AutoTokenizer.from_pretrained(model_dir, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(
    model_dir,
    device_map="cpu",
    trust_remote_code=True,
).eval()

# close to release resource
connector.close()

# do inference
```

### Vllm

```python
from transformers import AutoTokenizer
from vllm import LLM, SamplingParams
from ossmodelconnector import OssModelConnector

# initialize OssModelConnector
connector = OssModelConnector(...)

# prepare_directory
oss_path = "oss://ai-testset/qwen/Qwen25-75B"
model_dir = '/root/abc/'
connector.prepare_directory(oss_path, model_dir)

# pass model_dir to vllm
tokenizer = AutoTokenizer.from_pretrained(model_dir, trust_remote_code=True)
sampling_params = SamplingParams(temperature=0.7, top_p=0.8, repetition_penalty=1.05, max_tokens=512)
llm = LLM(model=model_dir, trust_remote_code=True)

# close to release resource
connector.close()

# do inference
```

# Stable Diffusion web UI

Edit launch.py to initalize and configure OssModelConnector.

```python
from modules import launch_utils

import oss2
from oss2.credentials import EnvironmentVariableCredentialsProvider
from ossmodelconnector import OssModelConnector

...

def main():
    ...


if __name__ == "__main__":
    connector = OssModelConnector(endpoint='oss-cn-beijing-internal.aliyuncs.com',
                                  cred_provider=EnvironmentVariableCredentialsProvider(),
                                  config_path='/etc/connector.json')
    connector.prepare_directory('oss://ai-testset/Stable-diffusion/', '/root/stable-diffusion-webui/models/Stable-diffusion')

    main()
```

Currently, prepare_directory() loads all models into memory, which can put pressure on memory and even cause crashes in scenarios with a large number of models. In the future, prepare_directory() will support lazy loading, downloading models only when switching to or open them, and it will include a garbage collection feature to release memory for unused models after a specified time.
