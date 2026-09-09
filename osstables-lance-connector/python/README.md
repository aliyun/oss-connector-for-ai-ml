# OssTables Lance Connector

Connect [Lance](https://lance.org) to the Alibaba Cloud **OssTables** catalog.

OssTables exposes a [Lance REST Namespace](https://lance.org/docs/namespace/) endpoint
secured with AWS Signature Version 4. This connector implements that namespace and signs
every request, so you can use OssTables from Lance, Spark, Trino and Ray with your normal
Alibaba Cloud credentials.

## Requirements

| Component | Version |
|---|---|
| Python | 3.9 or later |
| Java | 8 or later (tested on 17, 21 and 24) |

## Installation

**Python**

```bash
pip install --pre osstables-lance-connector
```

To read and write table data you also need Lance itself:

```bash
pip install pylance
```

**Java**

```xml
<dependency>
    <groupId>com.aliyun.osstables</groupId>
    <artifactId>osstables-lance-connector</artifactId>
    <version>1.0.0-rc2</version>
</dependency>
```

Arrow is a `provided` dependency, so add an Arrow allocator to your application:

```xml
<dependency>
    <groupId>org.apache.arrow</groupId>
    <artifactId>arrow-memory-netty</artifactId>
    <version>15.0.0</version>
    <scope>runtime</scope>
</dependency>
```

## Configuration

Every option uses the `osstables.` prefix.

| Option | Required | Default | Description |
|---|---|---|---|
| `osstables.uri` | yes | | Catalog endpoint, e.g. `https://my-bucket.cn-hangzhou.oss-tables.aliyuncs.com/lance` |
| `osstables.region` | yes | | Region used for request signing, e.g. `cn-hangzhou` |
| `osstables.access_key_id` | no | | Access key ID. Omit to use environment variables |
| `osstables.secret_access_key` | no | | Access key secret |
| `osstables.session_token` | no | | Security token, when using STS credentials |
| `osstables.delimiter` | no | `$` | Separator for multi-level table identifiers |
| `osstables.verify_ssl` | no | `true` | Verify TLS certificates; accepts only `true` or `false` |
| `osstables.service` | no | `osstables` | SigV4 service name; only `osstables` is accepted |
| `osstables.double_uri_encode` | no | `true` | Double-encode URI paths for SigV4; only `true` is accepted |

`osstables.service` and `osstables.double_uri_encode` are retained for compatibility with
older configurations, but OssTables requires their fixed values. The connector fails fast
if either option is set to another value. Setting `osstables.verify_ssl=false` disables both
certificate-chain and hostname verification; use it only for isolated testing, never in
production.

### Credentials

Credentials are taken from the first source that provides them:

1. The `osstables.access_key_id` and `osstables.secret_access_key` options above.
2. `ALIBABA_CLOUD_ACCESS_KEY_ID`, `ALIBABA_CLOUD_ACCESS_KEY_SECRET` and, optionally,
   `ALIBABA_CLOUD_SECURITY_TOKEN`.
3. `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and, optionally, `AWS_SESSION_TOKEN`.

Explicit access key ID and secret access key options must be provided together. Supplying
only one is an error and does not fall back to environment variables. When using temporary
credentials, supply the matching session token from the same source.

These credentials authenticate you to the **catalog**. Reading and writing table data goes
straight to OSS and is authorized separately, using the storage options shown under
"Reading and writing data" below.

## Getting started

### Python

```python
import lance_namespace
import osstables_lance_connector  # registers the "osstables" implementation
from lance_namespace import CreateNamespaceRequest, ListTablesRequest

namespace = lance_namespace.connect(
    "osstables",
    {
        "osstables.uri": "https://my-bucket.cn-hangzhou.oss-tables.aliyuncs.com/lance",
        "osstables.region": "cn-hangzhou",
        "osstables.access_key_id": "...",
        "osstables.secret_access_key": "...",
        # "osstables.session_token": "...",  # required for STS credentials
    },
)

namespace.create_namespace(CreateNamespaceRequest(id=["sales"]))
print(namespace.list_tables(ListTablesRequest(id=["sales"])).tables)
```

If you would rather not import the package, pass the class path to `connect` instead:

```python
namespace = lance_namespace.connect(
    "osstables_lance_connector.OssTablesNamespace", {...}
)
```

### Java

```java
import com.aliyun.osstables.lance.OssTablesNamespace;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
import org.apache.arrow.memory.RootAllocator;
import org.lance.namespace.LanceNamespace;
import org.lance.namespace.model.CreateNamespaceRequest;

Map<String, String> options = new HashMap<>();
options.put("osstables.uri", "https://my-bucket.cn-hangzhou.oss-tables.aliyuncs.com/lance");
options.put("osstables.region", "cn-hangzhou");
options.put("osstables.access_key_id", "...");
options.put("osstables.secret_access_key", "...");
// options.put("osstables.session_token", "..."); // required for STS credentials

try (RootAllocator allocator = new RootAllocator();
    OssTablesNamespace namespace =
        (OssTablesNamespace)
            LanceNamespace.connect(OssTablesNamespace.class.getName(), options, allocator)) {
    namespace.createNamespace(
        new CreateNamespaceRequest().id(Collections.singletonList("sales")));
}
```

## Reading and writing data

The catalog stores table metadata; the table data lives in OSS. Pass your OSS credentials
as storage options so Lance can reach the data files:

```python
import lance
import pyarrow as pa

storage_options = {
    "access_key_id": "...",
    "access_key_secret": "...",
    # "security_token": "...",  # required for STS credentials
    "endpoint": "https://oss-cn-hangzhou.aliyuncs.com",
    "region": "cn-hangzhou",
}

table = pa.table({"id": [1, 2, 3], "city": ["Hangzhou", "Beijing", "Shanghai"]})

lance.write_dataset(
    table,
    namespace_client=namespace,
    table_id=["sales", "orders"],
    mode="create",
    storage_options=storage_options,
)

dataset = lance.dataset(
    namespace_client=namespace,
    table_id=["sales", "orders"],
    storage_options=storage_options,
)
print(dataset.to_table())
```

Instead of passing `storage_options`, Lance can read OSS credentials and connection settings
from `OSS_ACCESS_KEY_ID`, `OSS_ACCESS_KEY_SECRET`, optional `OSS_SECURITY_TOKEN`,
`OSS_ENDPOINT` and `OSS_REGION`. These data-plane variables are independent of the catalog
credential variables described above.

## Query engines

Add the connector jar to the engine's class path and point the Lance catalog at this
implementation. Catalog credentials use the `osstables.` prefix; data access uses
`storage.`. With temporary credentials, configure both the catalog session token and the
OSS storage session token. If you use environment variables instead, make them available to
every process that accesses the catalog or data, including Spark drivers and executors or
Trino servers and workers.

### Spark

Every key is `spark.sql.catalog.<catalog-name>.<option>`, so an `osstables.` option
appears after the catalog name. `my_catalog` below is the name used in SQL and can be
anything.

```properties
spark.sql.catalog.my_catalog                             org.lance.spark.LanceNamespaceSparkCatalog
spark.sql.catalog.my_catalog.impl                        com.aliyun.osstables.lance.OssTablesNamespace
spark.sql.catalog.my_catalog.osstables.uri               https://my-bucket.cn-hangzhou.oss-tables.aliyuncs.com/lance
spark.sql.catalog.my_catalog.osstables.region            cn-hangzhou
spark.sql.catalog.my_catalog.osstables.access_key_id     ...
spark.sql.catalog.my_catalog.osstables.secret_access_key ...
spark.sql.catalog.my_catalog.osstables.session_token     ...
spark.sql.catalog.my_catalog.storage.access_key_id       ...
spark.sql.catalog.my_catalog.storage.access_key_secret   ...
spark.sql.catalog.my_catalog.storage.security_token      ...
spark.sql.catalog.my_catalog.storage.endpoint            https://oss-cn-hangzhou.aliyuncs.com
spark.sql.catalog.my_catalog.storage.region              cn-hangzhou
```

```sql
CREATE NAMESPACE my_catalog.sales;
CREATE TABLE my_catalog.sales.orders (id INT) USING lance;
SELECT * FROM my_catalog.sales.orders;
```

### Trino

`etc/catalog/my_catalog.properties`, where the file name is the catalog name in SQL:

```properties
connector.name=lance
lance.impl=com.aliyun.osstables.lance.OssTablesNamespace
lance.osstables.uri=https://my-bucket.cn-hangzhou.oss-tables.aliyuncs.com/lance
lance.osstables.region=cn-hangzhou
lance.osstables.access_key_id=...
lance.osstables.secret_access_key=...
lance.osstables.session_token=...
lance.storage.access_key_id=...
lance.storage.access_key_secret=...
lance.storage.security_token=...
lance.storage.endpoint=https://oss-cn-hangzhou.aliyuncs.com
lance.storage.region=cn-hangzhou
```

### Ray

```python
from lance_ray import read_lance

dataset = read_lance(
    table_id=["sales", "orders"],
    namespace_impl="osstables_lance_connector.OssTablesNamespace",
    namespace_properties={
        "osstables.uri": "https://my-bucket.cn-hangzhou.oss-tables.aliyuncs.com/lance",
        "osstables.region": "cn-hangzhou",
    },
    storage_options=storage_options,
)
```

## License

Released under the [MIT License](https://github.com/aliyun/oss-connector-for-ai-ml/blob/main/LICENSE).
