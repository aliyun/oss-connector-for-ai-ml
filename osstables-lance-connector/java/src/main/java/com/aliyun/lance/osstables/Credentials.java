package com.aliyun.lance.osstables;

import java.util.Objects;

/** Immutable AWS credentials (optionally with an STS session token). */
public final class Credentials {

  private final String accessKeyId;
  private final String secretAccessKey;
  private final String sessionToken;

  public Credentials(String accessKeyId, String secretAccessKey, String sessionToken) {
    this.accessKeyId = accessKeyId;
    this.secretAccessKey = secretAccessKey;
    this.sessionToken = sessionToken;
  }

  public String accessKeyId() {
    return accessKeyId;
  }

  public String secretAccessKey() {
    return secretAccessKey;
  }

  /** @return the STS session token, or {@code null} when using long-term credentials. */
  public String sessionToken() {
    return sessionToken;
  }

  @Override
  public boolean equals(Object o) {
    if (this == o) {
      return true;
    }
    if (!(o instanceof Credentials)) {
      return false;
    }
    Credentials that = (Credentials) o;
    return Objects.equals(accessKeyId, that.accessKeyId)
        && Objects.equals(secretAccessKey, that.secretAccessKey)
        && Objects.equals(sessionToken, that.sessionToken);
  }

  @Override
  public int hashCode() {
    return Objects.hash(accessKeyId, secretAccessKey, sessionToken);
  }
}
