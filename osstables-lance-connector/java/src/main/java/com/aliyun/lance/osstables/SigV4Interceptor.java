package com.aliyun.lance.osstables;

import java.io.IOException;
import java.time.Clock;
import java.util.Map;
import org.apache.hc.core5.http.ClassicHttpRequest;
import org.apache.hc.core5.http.EntityDetails;
import org.apache.hc.core5.http.HttpEntity;
import org.apache.hc.core5.http.HttpException;
import org.apache.hc.core5.http.HttpRequest;
import org.apache.hc.core5.http.HttpRequestInterceptor;
import org.apache.hc.core5.http.io.entity.EntityUtils;
import org.apache.hc.core5.http.protocol.HttpContext;
import org.apache.hc.core5.net.URIAuthority;

/**
 * SigV4-signs every outgoing request in the HttpClient pipeline.
 *
 * <p>Java analogue of the Python {@code SigV4ApiClient.call_api}: this runs where the request is
 * fully materialized (method, target URI, headers, and body bytes are final), so the payload hash
 * always matches the transmitted bytes — including Arrow IPC bodies for {@code create_table}. The
 * host is derived from the request authority rather than the Host header, so signing does not
 * depend on the order of the built-in protocol interceptors.
 */
final class SigV4Interceptor implements HttpRequestInterceptor {

  private final SigV4Signer signer;
  private final Clock clock;

  SigV4Interceptor(SigV4Signer signer, Clock clock) {
    this.signer = signer;
    this.clock = clock;
  }

  @Override
  public void process(HttpRequest request, EntityDetails entity, HttpContext context)
      throws HttpException, IOException {
    String requestUri = request.getRequestUri();
    String rawPath;
    String rawQuery;
    int q = requestUri.indexOf('?');
    if (q >= 0) {
      rawPath = requestUri.substring(0, q);
      rawQuery = requestUri.substring(q + 1);
    } else {
      rawPath = requestUri;
      rawQuery = "";
    }

    URIAuthority authority = request.getAuthority();
    String host = authority != null ? authority.getHostName() : "";
    int port = authority != null ? authority.getPort() : -1;
    String scheme = request.getScheme();

    byte[] payload = new byte[0];
    if (request instanceof ClassicHttpRequest) {
      HttpEntity body = ((ClassicHttpRequest) request).getEntity();
      if (body != null) {
        payload = EntityUtils.toByteArray(body);
      }
    }
    String contentType = entity != null ? entity.getContentType() : null;

    Map<String, String> signed =
        signer.sign(
            request.getMethod(),
            scheme,
            host,
            port,
            rawPath,
            rawQuery,
            contentType,
            payload,
            clock.instant());
    for (Map.Entry<String, String> h : signed.entrySet()) {
      request.setHeader(h.getKey(), h.getValue());
    }
  }
}
