package com.aliyun.lance.osstables;

import java.io.UnsupportedEncodingException;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

/**
 * Computes AWS Signature Version 4 signature headers for HTTP requests.
 *
 * <p>Ports {@code SigV4Signer} in the Python implementation. The public canonicalization
 * primitives are static so they can be asserted directly against the AWS documented test vector.
 * {@link #sign} operates on decomposed request parts (obtained from the HttpClient request in the
 * interceptor) rather than a URL string, so the payload hash is computed over the exact bytes
 * transmitted on the wire.
 */
public final class SigV4Signer {

  /**
   * Every property this implementation reads is namespaced with {@code osstables.} so it can never
   * be confused with the data-plane OSS options ({@code storage.} prefix / {@code storageOptions}).
   */
  public static final String PROPERTY_PREFIX = "osstables.";

  public static final String PROPERTY_REGION = PROPERTY_PREFIX + "region";
  public static final String PROPERTY_SERVICE = PROPERTY_PREFIX + "service";
  public static final String PROPERTY_ACCESS_KEY_ID = PROPERTY_PREFIX + "access_key_id";
  public static final String PROPERTY_SECRET_ACCESS_KEY = PROPERTY_PREFIX + "secret_access_key";
  public static final String PROPERTY_SESSION_TOKEN = PROPERTY_PREFIX + "session_token";
  public static final String PROPERTY_DOUBLE_URI_ENCODE = PROPERTY_PREFIX + "double_uri_encode";

  private static final String ALGORITHM = "AWS4-HMAC-SHA256";
  private static final DateTimeFormatter AMZ_DATE_FORMAT =
      DateTimeFormatter.ofPattern("yyyyMMdd'T'HHmmss'Z'").withZone(ZoneOffset.UTC);

  private final String region;
  private final String service;
  private final Credentials credentials;
  private final boolean doubleUriEncode;

  public SigV4Signer(
      String region, String service, Credentials credentials, boolean doubleUriEncode) {
    this.region = region;
    this.service = service;
    this.credentials = credentials;
    this.doubleUriEncode = doubleUriEncode;
  }

  /** Canonical request text plus its {@code SignedHeaders} value. */
  public static final class CanonicalRequest {
    public final String text;
    public final String signedHeaders;

    CanonicalRequest(String text, String signedHeaders) {
      this.text = text;
      this.signedHeaders = signedHeaders;
    }
  }

  /**
   * Compute the signature headers to add to a fully materialized request.
   *
   * @return headers to add: {@code x-amz-date}, {@code x-amz-content-sha256}, optional {@code
   *     x-amz-security-token}, and {@code Authorization}.
   */
  public Map<String, String> sign(
      String method,
      String scheme,
      String host,
      int port,
      String rawPath,
      String rawQuery,
      String contentType,
      byte[] payload,
      Instant now) {
    String amzDate = AMZ_DATE_FORMAT.format(now);
    String datestamp = amzDate.substring(0, 8);
    String payloadHash = sha256Hex(payload);

    Map<String, String> newHeaders = new TreeMap<>();
    newHeaders.put("x-amz-date", amzDate);
    newHeaders.put("x-amz-content-sha256", payloadHash);
    if (credentials.sessionToken() != null) {
      newHeaders.put("x-amz-security-token", credentials.sessionToken());
    }

    Map<String, String> headersToSign = new TreeMap<>();
    headersToSign.put("host", hostHeader(scheme, host, port));
    if (contentType != null) {
      headersToSign.put("content-type", contentType);
    }
    headersToSign.putAll(newHeaders);

    CanonicalRequest creq =
        canonicalRequest(method, rawPath, rawQuery, headersToSign, payloadHash, doubleUriEncode);
    String scope = datestamp + "/" + region + "/" + service + "/aws4_request";
    String sts = stringToSign(amzDate, scope, creq.text);
    byte[] key = signingKey(credentials.secretAccessKey(), datestamp, region, service);
    String signature = hexEncode(hmacSha256(key, sts));

    newHeaders.put(
        "Authorization",
        ALGORITHM
            + " Credential="
            + credentials.accessKeyId()
            + "/"
            + scope
            + ", SignedHeaders="
            + creq.signedHeaders
            + ", Signature="
            + signature);
    return newHeaders;
  }

  // ---- canonicalization primitives (public for direct test-vector assertions) ----

  /** Host header value: lowercase host, omitting the port when it is the scheme default. */
  public static String hostHeader(String scheme, String host, int port) {
    String h = host == null ? "" : host.toLowerCase();
    int defaultPort = "https".equalsIgnoreCase(scheme) ? 443 : "http".equalsIgnoreCase(scheme) ? 80 : -1;
    if (port != -1 && port != defaultPort) {
      return h + ":" + port;
    }
    return h;
  }

  /**
   * Build the canonical URI from the on-wire (already percent-encoded) path. With {@code
   * doubleUriEncode} (the default) each path segment is percent-encoded once more.
   */
  public static String canonicalUri(String rawPath, boolean doubleUriEncode) {
    if (rawPath == null || rawPath.isEmpty()) {
      return "/";
    }
    if (!doubleUriEncode) {
      return rawPath;
    }
    String[] segments = rawPath.split("/", -1);
    StringBuilder sb = new StringBuilder();
    for (int i = 0; i < segments.length; i++) {
      if (i > 0) {
        sb.append('/');
      }
      sb.append(PercentEncoder.encode(segments[i]));
    }
    return sb.toString();
  }

  /** Build the canonical query string: decode, re-encode, sort by encoded (key, value) pairs. */
  public static String canonicalQuery(String rawQuery) {
    if (rawQuery == null || rawQuery.isEmpty()) {
      return "";
    }
    List<String[]> encoded = new ArrayList<>();
    for (String segment : rawQuery.split("&", -1)) {
      if (segment.isEmpty()) {
        continue;
      }
      int eq = segment.indexOf('=');
      String rawKey = eq >= 0 ? segment.substring(0, eq) : segment;
      String rawVal = eq >= 0 ? segment.substring(eq + 1) : "";
      encoded.add(
          new String[] {
            PercentEncoder.encode(urlDecode(rawKey)), PercentEncoder.encode(urlDecode(rawVal))
          });
    }
    encoded.sort(
        (a, b) -> {
          int c = a[0].compareTo(b[0]);
          return c != 0 ? c : a[1].compareTo(b[1]);
        });
    StringBuilder sb = new StringBuilder();
    for (int i = 0; i < encoded.size(); i++) {
      if (i > 0) {
        sb.append('&');
      }
      sb.append(encoded.get(i)[0]).append('=').append(encoded.get(i)[1]);
    }
    return sb.toString();
  }

  /**
   * Build the SigV4 canonical request from decomposed parts.
   *
   * @param headersToSign header name/value pairs to sign (names are lowercased, values whitespace-collapsed)
   */
  public static CanonicalRequest canonicalRequest(
      String method,
      String rawPath,
      String rawQuery,
      Map<String, String> headersToSign,
      String payloadHash,
      boolean doubleUriEncode) {
    TreeMap<String, String> normalized = new TreeMap<>();
    for (Map.Entry<String, String> e : headersToSign.entrySet()) {
      normalized.put(e.getKey().toLowerCase(), collapseWhitespace(e.getValue()));
    }
    StringBuilder canonicalHeaders = new StringBuilder();
    StringBuilder signedHeaders = new StringBuilder();
    boolean first = true;
    for (Map.Entry<String, String> e : normalized.entrySet()) {
      canonicalHeaders.append(e.getKey()).append(':').append(e.getValue()).append('\n');
      if (!first) {
        signedHeaders.append(';');
      }
      signedHeaders.append(e.getKey());
      first = false;
    }
    String text =
        method.toUpperCase()
            + "\n"
            + canonicalUri(rawPath, doubleUriEncode)
            + "\n"
            + canonicalQuery(rawQuery)
            + "\n"
            + canonicalHeaders
            + "\n"
            + signedHeaders
            + "\n"
            + payloadHash;
    return new CanonicalRequest(text, signedHeaders.toString());
  }

  public static String stringToSign(String amzDate, String scope, String canonicalRequestText) {
    return ALGORITHM
        + "\n"
        + amzDate
        + "\n"
        + scope
        + "\n"
        + sha256Hex(canonicalRequestText.getBytes(StandardCharsets.UTF_8));
  }

  public static byte[] signingKey(
      String secretAccessKey, String datestamp, String region, String service) {
    byte[] kDate =
        hmacSha256(("AWS4" + secretAccessKey).getBytes(StandardCharsets.UTF_8), datestamp);
    byte[] kRegion = hmacSha256(kDate, region);
    byte[] kService = hmacSha256(kRegion, service);
    return hmacSha256(kService, "aws4_request");
  }

  public static String sha256Hex(byte[] data) {
    try {
      return hexEncode(MessageDigest.getInstance("SHA-256").digest(data));
    } catch (Exception e) {
      throw new IllegalStateException("SHA-256 unavailable", e);
    }
  }

  // ---- internals ----

  static byte[] hmacSha256(byte[] key, String msg) {
    try {
      Mac mac = Mac.getInstance("HmacSHA256");
      mac.init(new SecretKeySpec(key, "HmacSHA256"));
      return mac.doFinal(msg.getBytes(StandardCharsets.UTF_8));
    } catch (Exception e) {
      throw new IllegalStateException("HmacSHA256 unavailable", e);
    }
  }

  private static String urlDecode(String value) {
    try {
      return URLDecoder.decode(value, "UTF-8");
    } catch (UnsupportedEncodingException e) {
      throw new IllegalStateException(e);
    }
  }

  private static String collapseWhitespace(String value) {
    return value == null ? "" : String.join(" ", value.trim().split("\\s+"));
  }

  private static String hexEncode(byte[] bytes) {
    StringBuilder sb = new StringBuilder(bytes.length * 2);
    for (byte b : bytes) {
      sb.append(Character.forDigit((b >> 4) & 0xF, 16)).append(Character.forDigit(b & 0xF, 16));
    }
    return sb.toString();
  }
}
