package com.aliyun.osstables.lance;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Map;
import org.apache.hc.core5.http.ClassicHttpRequest;
import org.apache.hc.core5.http.ContentType;
import org.apache.hc.core5.http.io.entity.StringEntity;
import org.apache.hc.core5.http.io.support.ClassicRequestBuilder;
import org.apache.hc.core5.http.protocol.BasicHttpContext;
import org.junit.jupiter.api.Test;

/**
 * Verifies the interceptor extracts the on-wire request parts faithfully (Risk 1: the raw {@code
 * %24} in the path must survive to the signature) and signs over the exact body bytes.
 */
class SigV4InterceptorTest {

  private static final String HOST = "my-bucket.cn-hangzhou-internal.oss-tables.aliyuncs.com";
  private static final String URL =
      "https://" + HOST + "/lance/v1/table/my_db%24my_table/describe?delimiter=%24";
  private static final Instant NOW =
      OffsetDateTime.of(2026, 7, 28, 1, 2, 3, 0, ZoneOffset.UTC).toInstant();

  @Test
  void signsRawEncodedPathAndBody() throws Exception {
    byte[] payload = "{\"id\":[\"my_db\",\"my_table\"]}".getBytes(StandardCharsets.UTF_8);
    SigV4Signer signer =
        new SigV4Signer(
            "cn-hangzhou", "osstables", new Credentials("test-ak", "test-sk", null), true);
    SigV4Interceptor interceptor =
        new SigV4Interceptor(signer, Clock.fixed(NOW, ZoneOffset.UTC));

    ClassicHttpRequest request =
        ClassicRequestBuilder.create("POST")
            .setUri(URL)
            .setEntity(new StringEntity(new String(payload, StandardCharsets.UTF_8),
                ContentType.APPLICATION_JSON))
            .build();

    // Fidelity: the raw percent-encoded token must be preserved on the wire target.
    assertTrue(
        request.getRequestUri().contains("my_db%24my_table"),
        "raw %24 must be preserved, got: " + request.getRequestUri());

    interceptor.process(request, request.getEntity(), new BasicHttpContext());

    assertNotNull(request.getFirstHeader("Authorization"));
    assertEquals("20260728T010203Z", request.getFirstHeader("x-amz-date").getValue());
    assertEquals(
        SigV4Signer.sha256Hex(payload),
        request.getFirstHeader("x-amz-content-sha256").getValue());

    // The interceptor must have signed exactly the decomposed on-wire parts.
    String contentType = request.getEntity().getContentType();
    Map<String, String> expected =
        signer.sign(
            "POST",
            "https",
            HOST,
            -1,
            "/lance/v1/table/my_db%24my_table/describe",
            "delimiter=%24",
            contentType,
            payload,
            NOW);
    assertEquals(
        expected.get("Authorization"), request.getFirstHeader("Authorization").getValue());
  }
}
