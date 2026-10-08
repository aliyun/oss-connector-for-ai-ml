# OSS Connector for AI/ML

[ossconnector.github.io](https://ossconnector.github.io/)

## Overview

OSS Connector for AI/ML provides high-performance integrations for AI, ML, and table workloads on [Alibaba Cloud OSS (Object Storage Service)](https://www.alibabacloud.com/en/product/object-storage-service).

The repository contains three connectors:

- [OSS Torch Connector](https://aliyun.github.io/oss-connector-for-ai-ml/#/torchconnector/introduction) is dedicated to AI training scenarios, including loading [datasets](https://pytorch.org/docs/stable/data.html#dataset-types) from OSS and loading/saving checkpoints, distributed checkpoints, and safetensors from/to OSS.

- [OSS Model Connector](https://aliyun.github.io/oss-connector-for-ai-ml/#/modelconnector/introduction) focuses on AI inference scenarios, loading large model files from OSS into local AI inference frameworks.

- [OssTables Lance Connector](osstables-lance-connector/README.md) connects Lance, Spark, Trino, and Ray to the Alibaba Cloud OssTables catalog through a SigV4-authenticated Lance REST Namespace implementation for Python and Java.

The OSS Torch and OSS Model connectors use a C++ core built on [PhotonLibOS](https://github.com/alibaba/PhotonLibOS) and distribute native libraries in Python wheel packages. The OssTables Lance Connector is implemented separately in Python and Java.

For details about the OSS Torch and OSS Model connectors, refer to [ossconnector.github.io](https://ossconnector.github.io/) or [aliyun.github.io/oss-connector-for-ai-ml](https://aliyun.github.io/oss-connector-for-ai-ml). For OssTables, see the [OssTables Lance Connector documentation](osstables-lance-connector/README.md).


## Related

[OSS Connector for AI/ML 中文文档](https://help.aliyun.com/zh/oss/developer-reference/oss-connector-for-al-ml)

## License

This project is licensed under the terms of the [MIT License](LICENSE).
