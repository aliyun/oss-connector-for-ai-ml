package com.aliyun.lance.osstables;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.lance.namespace.errors.InvalidInputException;

/** Config parsing, namespaceId format, and id-string encoding. */
class OssTablesNamespaceInitTest {

  private static Map<String, String> baseProps() {
    Map<String, String> p = new HashMap<>();
    p.put(OssTablesNamespace.PROPERTY_URI, "https://bucket.cn-hangzhou-internal.oss-tables.aliyuncs.com/lance/");
    p.put(SigV4Signer.PROPERTY_REGION, "cn-hangzhou");
    p.put(SigV4Signer.PROPERTY_ACCESS_KEY_ID, "ak");
    p.put(SigV4Signer.PROPERTY_SECRET_ACCESS_KEY, "sk");
    return p;
  }

  @Test
  void namespaceIdFormatAndTrailingSlashStripped() {
    OssTablesNamespace ns = new OssTablesNamespace();
    ns.initialize(baseProps(), null);
    assertEquals(
        "OssTablesNamespace { uri: \"https://bucket.cn-hangzhou-internal.oss-tables.aliyuncs.com/lance\", "
            + "region: \"cn-hangzhou\", service: \"osstables\" }",
        ns.namespaceId());
  }

  @Test
  void missingUriRejected() {
    Map<String, String> p = baseProps();
    p.remove(OssTablesNamespace.PROPERTY_URI);
    assertThrows(InvalidInputException.class, () -> new OssTablesNamespace().initialize(p, null));
  }

  @Test
  void missingRegionRejected() {
    Map<String, String> p = baseProps();
    p.remove(SigV4Signer.PROPERTY_REGION);
    assertThrows(InvalidInputException.class, () -> new OssTablesNamespace().initialize(p, null));
  }

  @Test
  void idStringJoinsWithDelimiter() {
    OssTablesNamespace ns = new OssTablesNamespace();
    ns.initialize(baseProps(), null);
    assertEquals("my_db$my_table", ns.idString(Arrays.asList("my_db", "my_table")));
    assertEquals("$", ns.idString(Collections.emptyList()));
    assertThrows(InvalidInputException.class, () -> ns.idString(null));
  }

  @Test
  void customDelimiter() {
    Map<String, String> p = baseProps();
    p.put(OssTablesNamespace.PROPERTY_DELIMITER, ".");
    OssTablesNamespace ns = new OssTablesNamespace();
    ns.initialize(p, null);
    assertEquals("my_db.my_table", ns.idString(Arrays.asList("my_db", "my_table")));
  }
}
