package com.aliyun.lance.osstables;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.lance.namespace.LanceNamespace;
import org.lance.namespace.errors.TableNotFoundException;
import org.lance.namespace.errors.UnauthenticatedException;
import org.lance.namespace.model.CreateNamespaceRequest;
import org.lance.namespace.model.CreateTableRequest;
import org.lance.namespace.model.CreateTableResponse;
import org.lance.namespace.model.DeclareTableRequest;
import org.lance.namespace.model.DeclareTableResponse;
import org.lance.namespace.model.DescribeTableRequest;
import org.lance.namespace.model.DescribeTableResponse;

/**
 * Contract tests: run {@link OssTablesNamespace} against a local mock HTTP server that verifies
 * every request's SigV4 signature from the raw wire data (byte-consistency of the payload hash plus
 * a full signature recompute). Ports {@code test_namespace_contract.py}.
 */
class OssTablesNamespaceContractTest {

  private static final String TEST_AK = "contract-test-ak";
  private static final String TEST_SK = "contract-test-sk";
  private static final String TEST_REGION = "cn-hangzhou";
  private static final String TEST_SERVICE = "osstables";

  private static final Pattern AUTH_RE =
      Pattern.compile(
          "AWS4-HMAC-SHA256 "
              + "Credential=(?<ak>[^/]+)/(?<date>\\d{8})/(?<region>[^/]+)/(?<service>[^/]+)/aws4_request, "
              + "SignedHeaders=(?<signed>[^,]+), "
              + "Signature=(?<signature>[0-9a-f]{64})");

  private MockGateway gateway;

  @BeforeEach
  void start() throws IOException {
    gateway = new MockGateway();
  }

  @AfterEach
  void stop() {
    List<String> errors = gateway.verificationErrors;
    gateway.stop();
    assertTrue(errors.isEmpty(), String.join("\n", errors));
  }

  private LanceNamespace connect(String impl, Map<String, String> extra) {
    Map<String, String> props = new HashMap<>();
    props.put(OssTablesNamespace.PROPERTY_URI, gateway.uri());
    props.put(SigV4Signer.PROPERTY_REGION, TEST_REGION);
    props.put(SigV4Signer.PROPERTY_ACCESS_KEY_ID, TEST_AK);
    props.put(SigV4Signer.PROPERTY_SECRET_ACCESS_KEY, TEST_SK);
    props.putAll(extra);
    return LanceNamespace.connect(impl, props, null);
  }

  private LanceNamespace namespace() {
    Map<String, String> extra = new HashMap<>();
    extra.put(SigV4Signer.PROPERTY_SERVICE, TEST_SERVICE);
    return connect("com.aliyun.lance.osstables.OssTablesNamespace", extra);
  }

  @Test
  void connectByClassPath() {
    LanceNamespace ns = connect("com.aliyun.lance.osstables.OssTablesNamespace", Collections.emptyMap());
    assertTrue(ns.namespaceId().contains("OssTablesNamespace"));
  }

  @Test
  void describeTable() {
    DescribeTableResponse response =
        namespace().describeTable(new DescribeTableRequest().id(Arrays.asList("my_db", "my_table")));
    assertEquals("oss://bucket/my_db/my_table", response.getLocation());
    assertEquals(3L, response.getVersion());
    MockGateway.Recorded last = gateway.last();
    assertTrue(last.path.startsWith("/lance/v1/table/my_db%24my_table/describe"));
    assertTrue(last.path.contains("delimiter=%24"));
  }

  @Test
  void declareTable() {
    DeclareTableResponse response =
        namespace().declareTable(new DeclareTableRequest().id(Arrays.asList("my_db", "new_table")));
    assertEquals("oss://bucket/my_db/new_table", response.getLocation());
    assertTrue(gateway.last().path.startsWith("/lance/v1/table/my_db%24new_table/declare"));
  }

  @Test
  void createNamespace() {
    namespace().createNamespace(new CreateNamespaceRequest().id(Collections.singletonList("my_db")));
    assertTrue(gateway.last().path.startsWith("/lance/v1/namespace/my_db/create"));
  }

  @Test
  void createTableBinaryBody() {
    byte[] arrowIpc = new byte[8 + 256 * 4];
    byte[] magic = "ARROW1\u0000\u0000".getBytes(StandardCharsets.UTF_8);
    System.arraycopy(magic, 0, arrowIpc, 0, 8);
    for (int i = 0; i < 256 * 4; i++) {
      arrowIpc[8 + i] = (byte) (i % 256);
    }
    CreateTableResponse response =
        namespace()
            .createTable(
                new CreateTableRequest().id(Arrays.asList("my_db", "created")).mode("create"),
                arrowIpc);
    assertEquals("oss://bucket/my_db/created", response.getLocation());
    MockGateway.Recorded last = gateway.last();
    assertArrayEquals(arrowIpc, last.body);
    assertEquals("application/vnd.apache.arrow.stream", last.headers.get("content-type"));
    assertTrue(last.path.contains("mode=create"));
  }

  @Test
  void errorMappingTableNotFound() {
    LanceNamespace ns = namespace();
    assertThrows(
        TableNotFoundException.class,
        () -> ns.describeTable(new DescribeTableRequest().id(Arrays.asList("my_db", "missing"))));
  }

  @Test
  void sessionTokenHeaderSigned() {
    Map<String, String> extra = new HashMap<>();
    extra.put(SigV4Signer.PROPERTY_SESSION_TOKEN, "sts-session-token");
    LanceNamespace ns = connect("com.aliyun.lance.osstables.OssTablesNamespace", extra);
    ns.describeTable(new DescribeTableRequest().id(Arrays.asList("my_db", "my_table")));
    MockGateway.Recorded last = gateway.last();
    assertEquals("sts-session-token", last.headers.get("x-amz-security-token"));
    assertTrue(last.headers.get("authorization").contains("x-amz-security-token"));
  }

  @Test
  void badSecretRejectedByGateway() {
    Map<String, String> props = new HashMap<>();
    props.put(OssTablesNamespace.PROPERTY_URI, gateway.uri());
    props.put(SigV4Signer.PROPERTY_REGION, TEST_REGION);
    props.put(SigV4Signer.PROPERTY_ACCESS_KEY_ID, TEST_AK);
    props.put(SigV4Signer.PROPERTY_SECRET_ACCESS_KEY, "wrong-sk");
    LanceNamespace ns = LanceNamespace.connect("com.aliyun.lance.osstables.OssTablesNamespace", props, null);
    assertThrows(
        UnauthenticatedException.class,
        () -> ns.describeTable(new DescribeTableRequest().id(Arrays.asList("my_db", "my_table"))));
    gateway.verificationErrors.clear(); // expected failure; keep teardown green
  }

  // ---- mock gateway ----

  static final class MockGateway {
    final List<Recorded> requests = Collections.synchronizedList(new ArrayList<>());
    final List<String> verificationErrors = Collections.synchronizedList(new ArrayList<>());
    private final HttpServer server;

    static final class Recorded {
      final String method;
      final String path;
      final Map<String, String> headers;
      final byte[] body;

      Recorded(String method, String path, Map<String, String> headers, byte[] body) {
        this.method = method;
        this.path = path;
        this.headers = headers;
        this.body = body;
      }
    }

    MockGateway() throws IOException {
      server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
      server.createContext("/", this::handle);
      server.start();
    }

    String uri() {
      return "http://127.0.0.1:" + server.getAddress().getPort() + "/lance";
    }

    void stop() {
      server.stop(0);
    }

    Recorded last() {
      return requests.get(requests.size() - 1);
    }

    private void handle(HttpExchange exchange) throws IOException {
      try {
        String method = exchange.getRequestMethod();
        String rawPath = exchange.getRequestURI().getRawPath();
        String rawQuery = exchange.getRequestURI().getRawQuery();
        String fullPath = rawQuery == null ? rawPath : rawPath + "?" + rawQuery;
        byte[] body = readAll(exchange.getRequestBody());

        Map<String, String> headers = new HashMap<>();
        for (Map.Entry<String, List<String>> e : exchange.getRequestHeaders().entrySet()) {
          headers.put(e.getKey().toLowerCase(), e.getValue().get(0));
        }

        String error = verify(method, fullPath, headers, body);
        if (error != null) {
          verificationErrors.add(method + " " + fullPath + ": " + error);
          respond(exchange, 401, "{\"code\":16,\"error\":\"signature invalid: " + error + "\"}");
          return;
        }
        requests.add(new Recorded(method, fullPath, headers, body));
        route(exchange, rawPath);
      } finally {
        exchange.close();
      }
    }

    private void route(HttpExchange exchange, String path) throws IOException {
      if (path.equals("/lance/v1/table/my_db%24missing/describe")) {
        respond(exchange, 404, "{\"code\":4,\"error\":\"table not found\"}");
      } else if (path.endsWith("/describe") && path.contains("/table/")) {
        respond(
            exchange,
            200,
            "{\"location\":\"oss://bucket/my_db/my_table\",\"version\":3,\"storage_options\":{\"region\":\""
                + TEST_REGION
                + "\"}}");
      } else if (path.endsWith("/declare")) {
        respond(exchange, 200, "{\"location\":\"oss://bucket/my_db/new_table\"}");
      } else if (path.endsWith("/create") && path.contains("/namespace/")) {
        respond(exchange, 200, "{\"properties\":{}}");
      } else if (path.endsWith("/create") && path.contains("/table/")) {
        respond(exchange, 200, "{\"location\":\"oss://bucket/my_db/created\",\"version\":1}");
      } else {
        respond(exchange, 404, "{\"code\":4,\"error\":\"no route: " + path + "\"}");
      }
    }

    private static String verify(
        String method, String fullPath, Map<String, String> headers, byte[] body) {
      String auth = headers.get("authorization");
      if (auth == null) {
        return "missing Authorization header";
      }
      Matcher m = AUTH_RE.matcher(auth);
      if (!m.matches()) {
        return "malformed Authorization header: " + auth;
      }
      if (!m.group("ak").equals(TEST_AK)) {
        return "unexpected access key: " + m.group("ak");
      }
      if (!m.group("region").equals(TEST_REGION) || !m.group("service").equals(TEST_SERVICE)) {
        return "unexpected scope: " + auth;
      }
      String payloadHash = headers.get("x-amz-content-sha256");
      String actualHash = SigV4Signer.sha256Hex(body);
      if (!actualHash.equals(payloadHash)) {
        return "payload hash mismatch: header=" + payloadHash + " actual=" + actualHash;
      }

      int q = fullPath.indexOf('?');
      String path = q >= 0 ? fullPath.substring(0, q) : fullPath;
      String query = q >= 0 ? fullPath.substring(q + 1) : "";
      StringBuilder cUri = new StringBuilder();
      String[] segs = path.split("/", -1);
      for (int i = 0; i < segs.length; i++) {
        if (i > 0) {
          cUri.append('/');
        }
        cUri.append(PercentEncoder.encode(segs[i]));
      }
      String cQuery = SigV4Signer.canonicalQuery(query);

      String[] signedNames = m.group("signed").split(";");
      java.util.TreeMap<String, String> items = new java.util.TreeMap<>();
      for (String name : signedNames) {
        String value = headers.get(name.toLowerCase());
        if (value == null) {
          return "signed header " + name + " not present in request";
        }
        items.put(name.toLowerCase(), String.join(" ", value.trim().split("\\s+")));
      }
      StringBuilder cHeaders = new StringBuilder();
      for (Map.Entry<String, String> e : items.entrySet()) {
        cHeaders.append(e.getKey()).append(':').append(e.getValue()).append('\n');
      }

      String amzDate = headers.get("x-amz-date");
      if (amzDate == null || !amzDate.substring(0, 8).equals(m.group("date"))) {
        return "x-amz-date " + amzDate + " does not match credential date " + m.group("date");
      }
      String creq =
          method
              + "\n"
              + cUri
              + "\n"
              + cQuery
              + "\n"
              + cHeaders
              + "\n"
              + m.group("signed")
              + "\n"
              + payloadHash;
      String scope = m.group("date") + "/" + TEST_REGION + "/" + TEST_SERVICE + "/aws4_request";
      String sts =
          "AWS4-HMAC-SHA256\n"
              + amzDate
              + "\n"
              + scope
              + "\n"
              + SigV4Signer.sha256Hex(creq.getBytes(StandardCharsets.UTF_8));
      byte[] key = SigV4Signer.signingKey(TEST_SK, m.group("date"), TEST_REGION, TEST_SERVICE);
      StringBuilder expected = new StringBuilder();
      for (byte b : SigV4Signer.hmacSha256(key, sts)) {
        expected.append(String.format("%02x", b));
      }
      if (!expected.toString().equals(m.group("signature"))) {
        return "signature mismatch: expected="
            + expected
            + " got="
            + m.group("signature")
            + "\ncanonical request:\n"
            + creq;
      }
      return null;
    }

    private static void respond(HttpExchange exchange, int status, String json) throws IOException {
      byte[] data = json.getBytes(StandardCharsets.UTF_8);
      exchange.getResponseHeaders().set("Content-Type", "application/json");
      exchange.sendResponseHeaders(status, data.length);
      try (OutputStream os = exchange.getResponseBody()) {
        os.write(data);
      }
    }

    private static byte[] readAll(InputStream in) throws IOException {
      ByteArrayOutputStream out = new ByteArrayOutputStream();
      byte[] buf = new byte[4096];
      int n;
      while ((n = in.read(buf)) != -1) {
        out.write(buf, 0, n);
      }
      return out.toByteArray();
    }
  }
}
