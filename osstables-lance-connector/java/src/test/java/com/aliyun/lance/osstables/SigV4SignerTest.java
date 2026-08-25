package com.aliyun.lance.osstables;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.TreeMap;
import org.junit.jupiter.api.Test;

/**
 * SigV4 unit tests. Algorithm correctness is pinned against the AWS documented example (GET
 * https://iam.amazonaws.com/?Action=ListUsers&Version=2010-05-08). Ports {@code test_sigv4.py}.
 */
class SigV4SignerTest {

  // AWS documented example vector
  private static final String AWS_SK = "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY";
  private static final String AWS_REGION = "us-east-1";
  private static final String AWS_SERVICE = "iam";
  private static final String AWS_DATE = "20150830T123600Z";
  private static final String EMPTY_SHA256 =
      "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";
  private static final String EXPECTED_CANONICAL_REQUEST =
      "GET\n"
          + "/\n"
          + "Action=ListUsers&Version=2010-05-08\n"
          + "content-type:application/x-www-form-urlencoded; charset=utf-8\n"
          + "host:iam.amazonaws.com\n"
          + "x-amz-date:20150830T123600Z\n"
          + "\n"
          + "content-type;host;x-amz-date\n"
          + EMPTY_SHA256;
  private static final String EXPECTED_CREQ_HASH =
      "f536975d06c0309214f805bb90ccff089219ecd68b2577efef23edd43b7e1a59";
  private static final String EXPECTED_SIGNING_KEY_HEX =
      "c4afb1cc5771d871763a393e44b703571b55cc28424d1a5e86da6ed3c154a4b9";
  private static final String EXPECTED_SIGNATURE =
      "5d672d79c15b13162d9279b0855cfba6789a8edb4c82c400e06b5924a6f2b5d7";

  private static Map<String, String> awsHeaders() {
    Map<String, String> h = new LinkedHashMap<>();
    h.put("host", "iam.amazonaws.com");
    h.put("content-type", "application/x-www-form-urlencoded; charset=utf-8");
    h.put("x-amz-date", AWS_DATE);
    return h;
  }

  @Test
  void awsVectorCanonicalRequest() {
    SigV4Signer.CanonicalRequest creq =
        SigV4Signer.canonicalRequest(
            "GET", "/", "Action=ListUsers&Version=2010-05-08", awsHeaders(), EMPTY_SHA256, true);
    assertEquals(EXPECTED_CANONICAL_REQUEST, creq.text);
    assertEquals("content-type;host;x-amz-date", creq.signedHeaders);
    assertEquals(
        EXPECTED_CREQ_HASH, SigV4Signer.sha256Hex(creq.text.getBytes(java.nio.charset.StandardCharsets.UTF_8)));
  }

  @Test
  void awsVectorStringToSign() {
    SigV4Signer.CanonicalRequest creq =
        SigV4Signer.canonicalRequest(
            "GET", "/", "Action=ListUsers&Version=2010-05-08", awsHeaders(), EMPTY_SHA256, true);
    String scope = "20150830/" + AWS_REGION + "/" + AWS_SERVICE + "/aws4_request";
    String sts = SigV4Signer.stringToSign(AWS_DATE, scope, creq.text);
    assertEquals(
        "AWS4-HMAC-SHA256\n" + AWS_DATE + "\n" + scope + "\n" + EXPECTED_CREQ_HASH, sts);
  }

  @Test
  void awsVectorSigningKey() {
    byte[] key = SigV4Signer.signingKey(AWS_SK, "20150830", AWS_REGION, AWS_SERVICE);
    StringBuilder sb = new StringBuilder();
    for (byte b : key) {
      sb.append(String.format("%02x", b));
    }
    assertEquals(EXPECTED_SIGNING_KEY_HEX, sb.toString());
  }

  @Test
  void awsVectorFullSignature() {
    SigV4Signer.CanonicalRequest creq =
        SigV4Signer.canonicalRequest(
            "GET", "/", "Action=ListUsers&Version=2010-05-08", awsHeaders(), EMPTY_SHA256, true);
    String scope = "20150830/" + AWS_REGION + "/" + AWS_SERVICE + "/aws4_request";
    String sts = SigV4Signer.stringToSign(AWS_DATE, scope, creq.text);
    byte[] key = SigV4Signer.signingKey(AWS_SK, "20150830", AWS_REGION, AWS_SERVICE);
    StringBuilder sb = new StringBuilder();
    for (byte b : SigV4Signer.hmacSha256(key, sts)) {
      sb.append(String.format("%02x", b));
    }
    assertEquals(EXPECTED_SIGNATURE, sb.toString());
  }

  // ---- high-level signer (OssTable-style request) ----

  private static final String REGION = "cn-hangzhou";
  private static final String SERVICE = "osstables";
  private static final String HOST = "my-bucket.cn-hangzhou-internal.oss-tables.aliyuncs.com";
  private static final String RAW_PATH = "/lance/v1/table/my_db%24my_table/describe";
  private static final String RAW_QUERY = "delimiter=%24";
  private static final Instant NOW =
      OffsetDateTime.of(2026, 7, 28, 1, 2, 3, 0, ZoneOffset.UTC).toInstant();

  private SigV4Signer signer(String token) {
    return new SigV4Signer(REGION, SERVICE, new Credentials("test-ak", "test-sk", token), true);
  }

  @Test
  void signHeadersPresent() {
    byte[] payload = "{\"id\":[\"my_db\",\"my_table\"]}".getBytes(java.nio.charset.StandardCharsets.UTF_8);
    Map<String, String> r =
        signer(null)
            .sign("POST", "https", HOST, -1, RAW_PATH, RAW_QUERY, "application/json", payload, NOW);
    assertEquals("20260728T010203Z", r.get("x-amz-date"));
    assertEquals(SigV4Signer.sha256Hex(payload), r.get("x-amz-content-sha256"));
    assertTrue(
        r.get("Authorization")
            .startsWith(
                "AWS4-HMAC-SHA256 Credential=test-ak/20260728/cn-hangzhou/osstables/aws4_request, "
                    + "SignedHeaders=content-type;host;x-amz-content-sha256;x-amz-date, "
                    + "Signature="));
    assertFalse(r.containsKey("x-amz-security-token"));
  }

  @Test
  void signMatchesIndependentRecomputation() {
    byte[] payload = "{\"id\":[\"my_db\",\"my_table\"]}".getBytes(java.nio.charset.StandardCharsets.UTF_8);
    Map<String, String> r =
        signer(null)
            .sign("POST", "https", HOST, -1, RAW_PATH, RAW_QUERY, "application/json", payload, NOW);
    String expected =
        independentSignature(
            "POST", RAW_PATH, RAW_QUERY, HOST, "application/json", r, payload, "test-sk");
    assertTrue(r.get("Authorization").endsWith("Signature=" + expected));
  }

  @Test
  void sessionTokenSigned() {
    Map<String, String> r =
        signer("sts-token")
            .sign("POST", "https", HOST, -1, RAW_PATH, RAW_QUERY, "application/json",
                "{}".getBytes(java.nio.charset.StandardCharsets.UTF_8), NOW);
    assertEquals("sts-token", r.get("x-amz-security-token"));
    assertTrue(r.get("Authorization").contains("x-amz-security-token"));
  }

  @Test
  void binaryPayloadHash() {
    byte[] arrow = new byte[8 + 256];
    byte[] magic = "ARROW1\u0000\u0000".getBytes(java.nio.charset.StandardCharsets.UTF_8);
    System.arraycopy(magic, 0, arrow, 0, 8);
    for (int i = 0; i < 256; i++) {
      arrow[8 + i] = (byte) i;
    }
    Map<String, String> r =
        signer(null)
            .sign("POST", "https", HOST, -1, RAW_PATH, RAW_QUERY,
                "application/vnd.apache.arrow.stream", arrow, NOW);
    assertEquals(SigV4Signer.sha256Hex(arrow), r.get("x-amz-content-sha256"));
  }

  // ---- canonicalization ----

  @Test
  void hostThreeLevelDomain() {
    assertEquals(HOST, SigV4Signer.hostHeader("https", HOST, -1));
  }

  @Test
  void hostDefaultPortOmitted() {
    assertEquals("example.com", SigV4Signer.hostHeader("https", "example.com", 443));
    assertEquals("example.com", SigV4Signer.hostHeader("http", "example.com", 80));
  }

  @Test
  void hostCustomPortKept() {
    assertEquals("127.0.0.1:8080", SigV4Signer.hostHeader("http", "127.0.0.1", 8080));
  }

  @Test
  void canonicalUriDoubleEncode() {
    assertEquals(
        "/lance/v1/table/my_db%2524my_table/describe",
        SigV4Signer.canonicalUri("/lance/v1/table/my_db%24my_table/describe", true));
  }

  @Test
  void canonicalUriSingleEncode() {
    assertEquals(
        "/lance/v1/table/my_db%24my_table/describe",
        SigV4Signer.canonicalUri("/lance/v1/table/my_db%24my_table/describe", false));
  }

  @Test
  void canonicalUriEmpty() {
    assertEquals("/", SigV4Signer.canonicalUri("", true));
  }

  @Test
  void canonicalQuerySortedAndEncoded() {
    assertEquals("a=0&a=1&b=2&c=a%20b", SigV4Signer.canonicalQuery("b=2&a=1&a=0&c=a b"));
  }

  /** SigV4 re-implemented from scratch to cross-check {@link SigV4Signer#sign}. */
  private static String independentSignature(
      String method,
      String rawPath,
      String rawQuery,
      String host,
      String contentType,
      Map<String, String> signedResult,
      byte[] payload,
      String sk) {
    // canonical URI (double-encode each on-wire segment)
    StringBuilder cUri = new StringBuilder();
    String[] segs = rawPath.split("/", -1);
    for (int i = 0; i < segs.length; i++) {
      if (i > 0) {
        cUri.append('/');
      }
      cUri.append(PercentEncoder.encode(segs[i]));
    }
    // canonical query
    String cQuery = SigV4Signer.canonicalQuery(rawQuery);
    // signed headers = host, content-type, x-amz-content-sha256, x-amz-date
    TreeMap<String, String> h = new TreeMap<>();
    h.put("host", host);
    h.put("content-type", contentType);
    h.put("x-amz-date", signedResult.get("x-amz-date"));
    h.put("x-amz-content-sha256", signedResult.get("x-amz-content-sha256"));
    StringBuilder cHeaders = new StringBuilder();
    StringBuilder signed = new StringBuilder();
    boolean first = true;
    for (Map.Entry<String, String> e : h.entrySet()) {
      cHeaders.append(e.getKey()).append(':').append(e.getValue()).append('\n');
      if (!first) {
        signed.append(';');
      }
      signed.append(e.getKey());
      first = false;
    }
    String payloadHash = SigV4Signer.sha256Hex(payload);
    String creq =
        method + "\n" + cUri + "\n" + cQuery + "\n" + cHeaders + "\n" + signed + "\n" + payloadHash;
    String amzDate = signedResult.get("x-amz-date");
    String datestamp = amzDate.substring(0, 8);
    String scope = datestamp + "/" + REGION + "/" + SERVICE + "/aws4_request";
    String sts =
        "AWS4-HMAC-SHA256\n"
            + amzDate
            + "\n"
            + scope
            + "\n"
            + SigV4Signer.sha256Hex(creq.getBytes(java.nio.charset.StandardCharsets.UTF_8));
    byte[] key = SigV4Signer.signingKey(sk, datestamp, REGION, SERVICE);
    StringBuilder sb = new StringBuilder();
    for (byte b : SigV4Signer.hmacSha256(key, sts)) {
      sb.append(String.format("%02x", b));
    }
    return sb.toString();
  }
}
