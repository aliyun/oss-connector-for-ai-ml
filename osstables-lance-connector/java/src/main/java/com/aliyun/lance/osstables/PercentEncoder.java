package com.aliyun.lance.osstables;

import java.nio.charset.StandardCharsets;

/**
 * RFC 3986 percent-encoding with the AWS SigV4 unreserved safe set {@code A-Za-z0-9-._~}.
 *
 * <p>Ports Python {@code urllib.parse.quote(value, safe="-._~")}: every byte of the UTF-8
 * encoding except the unreserved set becomes {@code %XX} with uppercase hex; space becomes
 * {@code %20} (never {@code +}). {@link java.net.URLEncoder} is unsuitable (it emits {@code +}
 * for space and does not encode {@code *}), so this is implemented manually over UTF-8 bytes.
 */
final class PercentEncoder {

  private static final char[] HEX = "0123456789ABCDEF".toCharArray();

  private PercentEncoder() {}

  /** Percent-encodes {@code value}; every non-unreserved byte (including {@code /}) is escaped. */
  static String encode(String value) {
    byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
    StringBuilder sb = new StringBuilder(bytes.length);
    for (byte b : bytes) {
      int c = b & 0xFF;
      if (isUnreserved(c)) {
        sb.append((char) c);
      } else {
        sb.append('%').append(HEX[c >> 4]).append(HEX[c & 0x0F]);
      }
    }
    return sb.toString();
  }

  private static boolean isUnreserved(int c) {
    return (c >= 'A' && c <= 'Z')
        || (c >= 'a' && c <= 'z')
        || (c >= '0' && c <= '9')
        || c == '-'
        || c == '.'
        || c == '_'
        || c == '~';
  }
}
