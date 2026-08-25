package com.aliyun.lance.osstables;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.Closeable;
import java.io.IOException;
import java.time.Clock;
import java.util.List;
import java.util.Map;
import javax.net.ssl.SSLContext;
import org.apache.arrow.memory.BufferAllocator;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.client5.http.ssl.NoopHostnameVerifier;
import org.apache.hc.client5.http.ssl.SSLConnectionSocketFactory;
import org.apache.hc.core5.ssl.SSLContexts;
import org.lance.namespace.LanceNamespace;
import org.lance.namespace.client.apache.ApiClient;
import org.lance.namespace.client.apache.api.NamespaceApi;
import org.lance.namespace.client.apache.api.TableApi;
import org.lance.namespace.errors.InvalidInputException;
import org.lance.namespace.model.CreateNamespaceRequest;
import org.lance.namespace.model.CreateNamespaceResponse;
import org.lance.namespace.model.CreateTableRequest;
import org.lance.namespace.model.CreateTableResponse;
import org.lance.namespace.model.CreateTableVersionRequest;
import org.lance.namespace.model.CreateTableVersionResponse;
import org.lance.namespace.model.DeclareTableRequest;
import org.lance.namespace.model.DeclareTableResponse;
import org.lance.namespace.model.DeregisterTableRequest;
import org.lance.namespace.model.DeregisterTableResponse;
import org.lance.namespace.model.DescribeNamespaceRequest;
import org.lance.namespace.model.DescribeNamespaceResponse;
import org.lance.namespace.model.DescribeTableRequest;
import org.lance.namespace.model.DescribeTableResponse;
import org.lance.namespace.model.DescribeTableVersionRequest;
import org.lance.namespace.model.DescribeTableVersionResponse;
import org.lance.namespace.model.DropNamespaceRequest;
import org.lance.namespace.model.DropNamespaceResponse;
import org.lance.namespace.model.DropTableRequest;
import org.lance.namespace.model.DropTableResponse;
import org.lance.namespace.model.ListNamespacesRequest;
import org.lance.namespace.model.ListNamespacesResponse;
import org.lance.namespace.model.ListTableVersionsRequest;
import org.lance.namespace.model.ListTableVersionsResponse;
import org.lance.namespace.model.ListTablesRequest;
import org.lance.namespace.model.ListTablesResponse;
import org.lance.namespace.model.NamespaceExistsRequest;
import org.lance.namespace.model.RenameTableRequest;
import org.lance.namespace.model.RenameTableResponse;
import org.lance.namespace.model.TableExistsRequest;

/**
 * SigV4-signed Lance REST Namespace implementation for OssTable.
 *
 * <p>Loaded via {@code LanceNamespace.connect("com.aliyun.lance.osstables.OssTablesNamespace", props,
 * allocator)}, or via the {@code "osstables"} alias after calling {@link #register()}. Ports the
 * Python {@code OssTablesNamespace}.
 */
public class OssTablesNamespace implements LanceNamespace, Closeable {

  public static final String PROPERTY_URI = SigV4Signer.PROPERTY_PREFIX + "uri";
  public static final String PROPERTY_DELIMITER = SigV4Signer.PROPERTY_PREFIX + "delimiter";
  public static final String PROPERTY_VERIFY_SSL = SigV4Signer.PROPERTY_PREFIX + "verify_ssl";

  private static final ObjectMapper JSON = new ObjectMapper();

  private String uri;
  private String region;
  private String service;
  private String delimiter;
  private CloseableHttpClient httpClient;
  private NamespaceApi namespaceApi;
  private TableApi tableApi;

  /** Required public no-arg constructor for reflective construction by {@code connect}. */
  public OssTablesNamespace() {}

  /** Registers the {@code "osstables"} alias for this implementation. */
  public static void register() {
    LanceNamespace.registerNamespaceImpl("osstables", "com.aliyun.lance.osstables.OssTablesNamespace");
  }

  @Override
  public void initialize(Map<String, String> configProperties, BufferAllocator allocator) {
    this.uri = stripTrailingSlashes(required(configProperties, PROPERTY_URI));
    this.region = required(configProperties, SigV4Signer.PROPERTY_REGION);
    this.service =
        configProperties.getOrDefault(SigV4Signer.PROPERTY_SERVICE, "osstables");
    this.delimiter = configProperties.getOrDefault(PROPERTY_DELIMITER, "$");
    boolean doubleUriEncode =
        parseBoolean(configProperties.get(SigV4Signer.PROPERTY_DOUBLE_URI_ENCODE), true);
    boolean verifySsl = parseBoolean(configProperties.get(PROPERTY_VERIFY_SSL), true);

    Credentials credentials = CredentialsResolver.resolve(configProperties, EnvProvider.system());
    SigV4Signer signer = new SigV4Signer(region, service, credentials, doubleUriEncode);
    SigV4Interceptor interceptor = new SigV4Interceptor(signer, Clock.systemUTC());

    this.httpClient = buildHttpClient(interceptor, verifySsl);
    ApiClient apiClient = new ApiClient(httpClient);
    apiClient.setBasePath(uri);
    this.namespaceApi = new NamespaceApi(apiClient);
    this.tableApi = new TableApi(apiClient);
  }

  @Override
  public String namespaceId() {
    return "OssTablesNamespace { uri: \""
        + uri
        + "\", region: \""
        + region
        + "\", service: \""
        + service
        + "\" }";
  }

  @Override
  public void close() throws IOException {
    if (httpClient != null) {
      httpClient.close();
    }
  }

  // ---- namespace operations ----

  @Override
  public CreateNamespaceResponse createNamespace(CreateNamespaceRequest request) {
    return ErrorTranslator.translate(
        () -> namespaceApi.createNamespace(idString(request.getId()), request, delimiter));
  }

  @Override
  public DescribeNamespaceResponse describeNamespace(DescribeNamespaceRequest request) {
    return ErrorTranslator.translate(
        () -> namespaceApi.describeNamespace(idString(request.getId()), request, delimiter));
  }

  @Override
  public ListNamespacesResponse listNamespaces(ListNamespacesRequest request) {
    return ErrorTranslator.translate(
        () ->
            namespaceApi.listNamespaces(
                idString(request.getId()), delimiter, request.getPageToken(), request.getLimit()));
  }

  @Override
  public DropNamespaceResponse dropNamespace(DropNamespaceRequest request) {
    return ErrorTranslator.translate(
        () -> namespaceApi.dropNamespace(idString(request.getId()), request, delimiter));
  }

  @Override
  public void namespaceExists(NamespaceExistsRequest request) {
    ErrorTranslator.translateVoid(
        () -> namespaceApi.namespaceExists(idString(request.getId()), request, delimiter));
  }

  @Override
  public ListTablesResponse listTables(ListTablesRequest request) {
    return ErrorTranslator.translate(
        () ->
            namespaceApi.listTables(
                idString(request.getId()),
                delimiter,
                request.getPageToken(),
                request.getLimit(),
                request.getIncludeDeclared()));
  }

  // ---- table operations ----

  @Override
  public DescribeTableResponse describeTable(DescribeTableRequest request) {
    return ErrorTranslator.translate(
        () ->
            tableApi.describeTable(
                idString(request.getId()),
                request,
                delimiter,
                request.getWithTableUri(),
                request.getLoadDetailedMetadata(),
                request.getCheckDeclared()));
  }

  @Override
  public DeclareTableResponse declareTable(DeclareTableRequest request) {
    return ErrorTranslator.translate(
        () -> tableApi.declareTable(idString(request.getId()), request, delimiter));
  }

  @Override
  public CreateTableResponse createTable(CreateTableRequest request, byte[] requestData) {
    return ErrorTranslator.translate(
        () ->
            tableApi.createTable(
                idString(request.getId()),
                requestData,
                delimiter,
                request.getMode(),
                jsonOrNull(request.getProperties()),
                jsonOrNull(request.getStorageOptions())));
  }

  @Override
  public DropTableResponse dropTable(DropTableRequest request) {
    return ErrorTranslator.translate(
        () -> tableApi.dropTable(idString(request.getId()), delimiter));
  }

  @Override
  public void tableExists(TableExistsRequest request) {
    ErrorTranslator.translateVoid(
        () -> tableApi.tableExists(idString(request.getId()), request, delimiter));
  }

  @Override
  public DeregisterTableResponse deregisterTable(DeregisterTableRequest request) {
    return ErrorTranslator.translate(
        () -> tableApi.deregisterTable(idString(request.getId()), request, delimiter));
  }

  @Override
  public RenameTableResponse renameTable(RenameTableRequest request) {
    return ErrorTranslator.translate(
        () -> tableApi.renameTable(idString(request.getId()), request, delimiter));
  }

  @Override
  public ListTablesResponse listAllTables(ListTablesRequest request) {
    return ErrorTranslator.translate(
        () ->
            tableApi.listAllTables(
                delimiter, request.getPageToken(), request.getLimit(), request.getIncludeDeclared()));
  }

  @Override
  public DescribeTableVersionResponse describeTableVersion(DescribeTableVersionRequest request) {
    return ErrorTranslator.translate(
        () -> tableApi.describeTableVersion(idString(request.getId()), request, delimiter));
  }

  @Override
  public CreateTableVersionResponse createTableVersion(CreateTableVersionRequest request) {
    return ErrorTranslator.translate(
        () -> tableApi.createTableVersion(idString(request.getId()), request, delimiter));
  }

  @Override
  public ListTableVersionsResponse listTableVersions(ListTableVersionsRequest request) {
    return ErrorTranslator.translate(
        () ->
            tableApi.listTableVersions(
                idString(request.getId()),
                delimiter,
                request.getBranch(),
                request.getPageToken(),
                request.getLimit(),
                request.getDescending()));
  }

  // ---- helpers used by operations ----

  /** Join id parts with the delimiter; empty list yields the bare delimiter; null is an error. */
  String idString(List<String> idParts) {
    if (idParts == null) {
      throw new InvalidInputException("Object ID is required");
    }
    if (idParts.isEmpty()) {
      return delimiter;
    }
    return String.join(delimiter, idParts);
  }

  private static String jsonOrNull(Map<String, String> map) {
    if (map == null || map.isEmpty()) {
      return null;
    }
    try {
      return JSON.writeValueAsString(map);
    } catch (JsonProcessingException e) {
      throw new InvalidInputException("Failed to serialize map to JSON: " + e.getMessage());
    }
  }

  // ---- helpers ----

  private static CloseableHttpClient buildHttpClient(
      SigV4Interceptor interceptor, boolean verifySsl) {
    if (verifySsl) {
      return HttpClients.custom().addRequestInterceptorLast(interceptor).build();
    }
    try {
      SSLContext sslContext =
          SSLContexts.custom().loadTrustMaterial(null, (chain, authType) -> true).build();
      SSLConnectionSocketFactory sslsf =
          new SSLConnectionSocketFactory(sslContext, NoopHostnameVerifier.INSTANCE);
      return HttpClients.custom()
          .setConnectionManager(
              PoolingHttpClientConnectionManagerBuilder.create().setSSLSocketFactory(sslsf).build())
          .addRequestInterceptorLast(interceptor)
          .build();
    } catch (Exception e) {
      throw new IllegalStateException("Failed to configure trust-all TLS", e);
    }
  }

  private static String required(Map<String, String> props, String key) {
    String value = props.get(key);
    if (value == null || value.isEmpty()) {
      throw new InvalidInputException("Property '" + key + "' is required");
    }
    return value;
  }

  private static String stripTrailingSlashes(String value) {
    int end = value.length();
    while (end > 0 && value.charAt(end - 1) == '/') {
      end--;
    }
    return value.substring(0, end);
  }

  private static boolean parseBoolean(String value, boolean defaultValue) {
    if (value == null) {
      return defaultValue;
    }
    String lower = value.toLowerCase();
    return !(lower.equals("false") || lower.equals("0") || lower.equals("no"));
  }
}
