# OssTables Lance Connector

Connect [Lance](https://lance.org) to the Alibaba Cloud **OSS Tables** catalog.

OSS Tables exposes a [Lance REST Namespace](https://lance.org/docs/namespace/) endpoint
secured with AWS Signature Version 4. This connector implements that namespace and signs
every request, so you can use OSS Tables from Lance, Spark, Trino and Ray with your normal
Alibaba Cloud credentials.

## Requirements

| | |
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
    <groupId>com.aliyun.lance</groupId>
    <artifactId>osstables-lance-connector</artifactId>
    <version>0.1.0-rc1</version>
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
| `osstables.service` | no | `osstables` | Service name used for request signing |
| `osstables.delimiter` | no | `$` | Separator for multi-level table identifiers |
| `osstables.verify_ssl` | no | `true` | Set to `false` to skip TLS certificate verification |

### Credentials

Credentials are taken from the first source that provides them:

1. The `osstables.access_key_id` and `osstables.secret_access_key` options above.
2. `ALIBABA_CLOUD_ACCESS_KEY_ID`, `ALIBABA_CLOUD_ACCESS_KEY_SECRET` and, optionally,
   `ALIBABA_CLOUD_SECURITY_TOKEN`.
3. `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and, optionally, `AWS_SESSION_TOKEN`.

These credentials authenticate you to the **catalog**. Reading and writing table data goes
straight to OSS and is authorized separately — see
[Reading and writing data](#reading-and-writing-data).

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
import com.aliyun.lance.osstables.OssTablesNamespace;
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

try (RootAllocator allocator = new RootAllocator()) {
    LanceNamespace namespace =
        LanceNamespace.connect(OssTablesNamespace.class.getName(), options, allocator);

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

## Query engines

Add the connector jar to the engine's class path and point the Lance catalog at this
implementation. Catalog credentials use the `osstables.` prefix; data access uses
`storage.`.

### Spark

```properties
spark.sql.catalog.osstables                             org.lance.spark.LanceNamespaceSparkCatalog
spark.sql.catalog.osstables.impl                        com.aliyun.lance.osstables.OssTablesNamespace
spark.sql.catalog.osstables.osstables.uri               https://my-bucket.cn-hangzhou.oss-tables.aliyuncs.com/lance
spark.sql.catalog.osstables.osstables.region            cn-hangzhou
spark.sql.catalog.osstables.osstables.access_key_id     ...
spark.sql.catalog.osstables.osstables.secret_access_key ...
spark.sql.catalog.osstables.storage.access_key_id       ...
spark.sql.catalog.osstables.storage.access_key_secret   ...
spark.sql.catalog.osstables.storage.endpoint            https://oss-cn-hangzhou.aliyuncs.com
spark.sql.catalog.osstables.storage.region              cn-hangzhou
```

```sql
CREATE NAMESPACE osstables.sales;
CREATE TABLE osstables.sales.orders (id INT) USING lance;
SELECT * FROM osstables.sales.orders;
```

### Trino

`etc/catalog/osstables.properties`:

```properties
connector.name=lance
lance.impl=com.aliyun.lance.osstables.OssTablesNamespace
lance.osstables.uri=https://my-bucket.cn-hangzhou.oss-tables.aliyuncs.com/lance
lance.osstables.region=cn-hangzhou
lance.osstables.access_key_id=...
lance.osstables.secret_access_key=...
lance.storage.access_key_id=...
lance.storage.access_key_secret=...
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

## Building from source

```bash
# Python
cd python
pip install -e ".[dev]"
pytest

# Java
cd java
mvn test           # run the test suite
mvn package        # build the jar
```

## License

Released under the [MIT License](../LICENSE).
