package com.aliyun.lance.osstables;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.lance.namespace.errors.InvalidInputException;

/** Credential resolution order: explicit properties, then ALIBABA_CLOUD_*, then AWS_*. */
class CredentialsResolverTest {

  private static EnvProvider env(Map<String, String> values) {
    return values::get;
  }

  private static final EnvProvider EMPTY_ENV = env(new HashMap<>());

  @Test
  void explicit() {
    Map<String, String> props = new HashMap<>();
    props.put(SigV4Signer.PROPERTY_ACCESS_KEY_ID, "ak");
    props.put(SigV4Signer.PROPERTY_SECRET_ACCESS_KEY, "sk");
    props.put(SigV4Signer.PROPERTY_SESSION_TOKEN, "t");
    assertEquals(new Credentials("ak", "sk", "t"), CredentialsResolver.resolve(props, EMPTY_ENV));
  }

  @Test
  void explicitPartialRejected() {
    Map<String, String> props = new HashMap<>();
    props.put(SigV4Signer.PROPERTY_ACCESS_KEY_ID, "ak");
    assertThrows(
        InvalidInputException.class, () -> CredentialsResolver.resolve(props, EMPTY_ENV));
  }

  @Test
  void awsEnv() {
    Map<String, String> e = new HashMap<>();
    e.put("AWS_ACCESS_KEY_ID", "env-ak");
    e.put("AWS_SECRET_ACCESS_KEY", "env-sk");
    assertEquals(
        new Credentials("env-ak", "env-sk", null),
        CredentialsResolver.resolve(new HashMap<>(), env(e)));
  }

  @Test
  void alibabaEnv() {
    Map<String, String> e = new HashMap<>();
    e.put("ALIBABA_CLOUD_ACCESS_KEY_ID", "ali-ak");
    e.put("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "ali-sk");
    e.put("ALIBABA_CLOUD_SECURITY_TOKEN", "ali-token");
    assertEquals(
        new Credentials("ali-ak", "ali-sk", "ali-token"),
        CredentialsResolver.resolve(new HashMap<>(), env(e)));
  }

  @Test
  void alibabaTakesPrecedenceOverAws() {
    Map<String, String> e = new HashMap<>();
    e.put("ALIBABA_CLOUD_ACCESS_KEY_ID", "ali-ak");
    e.put("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "ali-sk");
    e.put("AWS_ACCESS_KEY_ID", "aws-ak");
    e.put("AWS_SECRET_ACCESS_KEY", "aws-sk");
    assertEquals(
        new Credentials("ali-ak", "ali-sk", null),
        CredentialsResolver.resolve(new HashMap<>(), env(e)));
  }

  @Test
  void missing() {
    assertThrows(
        InvalidInputException.class,
        () -> CredentialsResolver.resolve(new HashMap<>(), EMPTY_ENV));
  }

  @Test
  void toStringRedactsSecretAndToken() {
    String text = new Credentials("ak", "super-secret", "super-token").toString();
    assertFalse(text.contains("super-secret"));
    assertFalse(text.contains("super-token"));
    assertTrue(text.contains("ak"));
  }

  @Test
  void toStringMarksAbsentTokenAsNull() {
    assertTrue(new Credentials("ak", "sk", null).toString().contains("sessionToken=null"));
  }
}
