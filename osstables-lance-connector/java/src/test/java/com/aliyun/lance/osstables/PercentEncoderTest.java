package com.aliyun.lance.osstables;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

/** Ports {@code PercentEncoder} coverage from the Python test suite. */
class PercentEncoderTest {

  @Test
  void unreservedPassthrough() {
    assertEquals("-._~AZaz09", PercentEncoder.encode("-._~AZaz09"));
  }

  @Test
  void spaceBecomesPercent20() {
    assertEquals("a%20b", PercentEncoder.encode("a b"));
  }

  @Test
  void dollarEncodedUppercaseHex() {
    assertEquals("my_db%24my_table", PercentEncoder.encode("my_db$my_table"));
    assertTrue(PercentEncoder.encode("$").equals("%24"));
  }

  @Test
  void slashEncoded() {
    assertEquals("a%2Fb", PercentEncoder.encode("a/b"));
  }

  @Test
  void multibyteUtf8() {
    assertEquals("caf%C3%A9", PercentEncoder.encode("caf\u00e9"));
  }
}
