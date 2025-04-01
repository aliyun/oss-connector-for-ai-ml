
# OSS Model Connector

## Overview

Storing (large) models on a lower-cost object storage (like Alibaba Cloud OSS) is a cost-effective option. The OSS Model Connector provides high-performance methods for loading (large) model files from OSS in AI inference scenarios.

In current, memory of computing nodes for AI inference are generally large. The common practice is to first load the model from network storage or local disk into the node's memory before applying it for subsequent use.
The primary function of the OSS Model Connector is to fully leverage local memory to accelerate the process of downloading models from OSS.
In our testing environment, the download speed can exceed 15GB/s, approaching 20GB/s.

The OSS Model Connector mainly offers 3 usage methods.

- The first method is using the Python interface, allowing users to open OSS objects and read their contents through list stream api.
We also provide an interface for listing objects on OSS, as well as an implementation call 'fast list', which can complete the listing of a million objects within several seconds.

- The second method is utilizing the libraries for loading models in inference frameworks such as transformer or vllm. This method enables the integration of model file downloading and loading, optimizing the model deployment time.

- The third method is to use LD_PRELOAD to address scenarios that the second method cannot handle, such as multi-process environments. The advantage of this approach is that it does not require modifying the code, configuration alone is sufficient.

## Features

Compared to other solutions for loading OSS data, the OSS Model Connector is more focused, simpler, and high-performance.

- Focus

    Unlike [ossfs](https://github.com/aliyun/ossfs), which provides a generic POSIX interface, the OSS Model Connector is more focused on AI inference scenarios. In this context, only data reading is involved, so there is no need to implement complex write operations. Additionally, memory resources are usually more abundant in these scenarios, allowing for the use of large amounts of memory for caching to accelerate the speed of data downloading from OSS.

- Simpler

    The OSS Model Connector is used as an SDK, implemented entirely in user space, without the need for kernel or FUSE modules, resulting in a more simpler I/O path.

- High-performance

    Thanks to the simpler I/O path and efficient C++ implementation, the OSS Model Connector can achieve better performance. The C++ code is implemented based on the high-performance [PhotonLibOS](https://github.com/alibaba/PhotonLibOS), which includes features such as coroutines and HTTP client. In our testing environment, the model loading speed can exceed 15GB/s, approaching 20GB/s, achieve the maximum bandwidth of the OSS server configuration.
