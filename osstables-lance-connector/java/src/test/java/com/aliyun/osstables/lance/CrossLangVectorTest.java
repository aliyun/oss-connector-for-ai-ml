package com.aliyun.osstables.lance;

import static org.junit.jupiter.api.Assertions.assertEquals;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.InputStream;
import java.net.URI;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.DynamicTest;
import org.junit.jupiter.api.TestFactory;

/**
 * Cross-language SigV4 conformance. Asserts the Java signer produces byte-identical results to the
 * shared {@code sigv4_vectors.json} (generated from the Python reference implementation), so both
 * languages stay in lockstep.
 */
class CrossLangVectorTest {

  private static JsonNode vectors;
  private static final DateTimeFormatter AMZ =
      DateTimeFormatter.ofPattern("yyyyMMdd'T'HHmmss'Z'").withZone(ZoneOffset.UTC);

  @BeforeAll
  static void load() throws Exception {
    try (InputStream in = CrossLangVectorTest.class.getResourceAsStream("/sigv4_vectors.json")) {
      vectors = new ObjectMapper().readTree(in);
    }
  }

  @TestFactory
  List<DynamicTest> percentEncoder() {
    List<DynamicTest> tests = new ArrayList<>();
    for (JsonNode c : vectors.get("percent_encoder")) {
      tests.add(
          DynamicTest.dynamicTest(
              "encode:" + c.get("input").asText(),
              () ->
                  assertEquals(
                      c.get("expected").asText(),
                      PercentEncoder.encode(c.get("input").asText()))));
    }
    return tests;
  }

  @TestFactory
  List<DynamicTest> canonicalUri() {
    List<DynamicTest> tests = new ArrayList<>();
    for (JsonNode c : vectors.get("canonical_uri")) {
      tests.add(
          DynamicTest.dynamicTest(
              "uri:" + c.get("raw_path").asText() + ":" + c.get("double_uri_encode").asBoolean(),
              () ->
                  assertEquals(
                      c.get("expected").asText(),
                      SigV4Signer.canonicalUri(
                          c.get("raw_path").asText(), c.get("double_uri_encode").asBoolean()))));
    }
    return tests;
  }

  @TestFactory
  List<DynamicTest> canonicalQuery() {
    List<DynamicTest> tests = new ArrayList<>();
    for (JsonNode c : vectors.get("canonical_query")) {
      tests.add(
          DynamicTest.dynamicTest(
              "query:" + c.get("raw_query").asText(),
              () ->
                  assertEquals(
                      c.get("expected").asText(),
                      SigV4Signer.canonicalQuery(c.get("raw_query").asText()))));
    }
    return tests;
  }

  @TestFactory
  List<DynamicTest> hostHeader() {
    List<DynamicTest> tests = new ArrayList<>();
    for (JsonNode c : vectors.get("host_header")) {
      tests.add(
          DynamicTest.dynamicTest(
              "host:" + c.get("url").asText(),
              () -> {
                URI u = URI.create(c.get("url").asText());
                assertEquals(
                    c.get("expected").asText(),
                    SigV4Signer.hostHeader(u.getScheme(), u.getHost(), u.getPort()));
              }));
    }
    return tests;
  }

  @TestFactory
  List<DynamicTest> signingKey() {
    List<DynamicTest> tests = new ArrayList<>();
    for (JsonNode c : vectors.get("signing_key")) {
      tests.add(
          DynamicTest.dynamicTest(
              "signingKey:" + c.get("region").asText(),
              () -> {
                byte[] key =
                    SigV4Signer.signingKey(
                        c.get("secret_access_key").asText(),
                        c.get("datestamp").asText(),
                        c.get("region").asText(),
                        c.get("service").asText());
                StringBuilder sb = new StringBuilder();
                for (byte b : key) {
                  sb.append(String.format("%02x", b));
                }
                assertEquals(c.get("expected_hex").asText(), sb.toString());
              }));
    }
    return tests;
  }

  @TestFactory
  List<DynamicTest> signature() {
    List<DynamicTest> tests = new ArrayList<>();
    for (JsonNode c : vectors.get("signature")) {
      tests.add(
          DynamicTest.dynamicTest(
              "signature:" + c.get("name").asText(),
              () -> {
                URI u = URI.create(c.get("url").asText());
                String token = c.get("session_token").isNull() ? null : c.get("session_token").asText();
                String contentType =
                    c.get("content_type").isNull() ? null : c.get("content_type").asText();
                SigV4Signer signer =
                    new SigV4Signer(
                        c.get("region").asText(),
                        c.get("service").asText(),
                        new Credentials(
                            c.get("access_key_id").asText(),
                            c.get("secret_access_key").asText(),
                            token),
                        c.get("double_uri_encode").asBoolean());
                Instant now =
                    LocalDateTime.parse(c.get("amz_date").asText(), AMZ)
                        .toInstant(ZoneOffset.UTC);
                byte[] payload = hexToBytes(c.get("payload_hex").asText());
                Map<String, String> r =
                    signer.sign(
                        c.get("method").asText(),
                        u.getScheme(),
                        u.getHost(),
                        u.getPort(),
                        u.getRawPath(),
                        u.getRawQuery(),
                        contentType,
                        payload,
                        now);
                assertEquals(
                    c.get("expected_authorization").asText(),
                    r.get("Authorization"),
                    "authorization mismatch for " + c.get("name").asText());
              }));
    }
    return tests;
  }

  private static byte[] hexToBytes(String hex) {
    int len = hex.length();
    byte[] out = new byte[len / 2];
    for (int i = 0; i < len; i += 2) {
      out[i / 2] =
          (byte) ((Character.digit(hex.charAt(i), 16) << 4) + Character.digit(hex.charAt(i + 1), 16));
    }
    return out;
  }
}
