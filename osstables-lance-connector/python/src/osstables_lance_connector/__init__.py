"""OSS Tables connector for Lance: a SigV4-signed Lance REST Namespace client.

Importing this package registers the ``osstables`` alias, so both forms work:

    lance_namespace.connect("osstables_lance_connector.OssTablesNamespace", props)

    import osstables_lance_connector  # registers the alias
    lance_namespace.connect("osstables", props)
"""

from lance_namespace import register_namespace_impl

from .namespace import OssTablesNamespace
from .sigv4 import Credentials, SigV4ApiClient, SigV4Signer, resolve_credentials

__version__ = "0.1.0rc1"

__all__ = [
    "OssTablesNamespace",
    "Credentials",
    "SigV4Signer",
    "SigV4ApiClient",
    "resolve_credentials",
    "__version__",
]

register_namespace_impl("osstables", "osstables_lance_connector.OssTablesNamespace")
