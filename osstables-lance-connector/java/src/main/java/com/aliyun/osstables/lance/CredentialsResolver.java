package com.aliyun.osstables.lance;

import java.util.Map;
import org.lance.namespace.errors.InvalidInputException;

/**
 * Resolves {@link Credentials} from explicit properties, then environment variables.
 *
 * <p>Order:
 *
 * <ol>
 *   <li>Explicit {@code osstables.access_key_id} / {@code osstables.secret_access_key} /
 *       {@code osstables.session_token} properties (supplying only one of AK/SK is an error).
 *   <li>{@code ALIBABA_CLOUD_ACCESS_KEY_ID} / {@code ALIBABA_CLOUD_ACCESS_KEY_SECRET} / {@code
 *       ALIBABA_CLOUD_SECURITY_TOKEN}.
 *   <li>{@code AWS_ACCESS_KEY_ID} / {@code AWS_SECRET_ACCESS_KEY} / {@code AWS_SESSION_TOKEN}.
 * </ol>
 */
final class CredentialsResolver {

  private CredentialsResolver() {}

  static Credentials resolve(Map<String, String> properties, EnvProvider env) {
    String ak = emptyToNull(properties.get(SigV4Signer.PROPERTY_ACCESS_KEY_ID));
    String sk = emptyToNull(properties.get(SigV4Signer.PROPERTY_SECRET_ACCESS_KEY));
    String token = emptyToNull(properties.get(SigV4Signer.PROPERTY_SESSION_TOKEN));
    if (ak != null && sk != null) {
      return new Credentials(ak, sk, token);
    }
    if (ak != null || sk != null) {
      throw new InvalidInputException(
          "Both "
              + SigV4Signer.PROPERTY_ACCESS_KEY_ID
              + " and "
              + SigV4Signer.PROPERTY_SECRET_ACCESS_KEY
              + " must be provided together");
    }

    String[][] envTuples = {
      {
        "ALIBABA_CLOUD_ACCESS_KEY_ID",
        "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
        "ALIBABA_CLOUD_SECURITY_TOKEN"
      },
      {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"},
    };
    for (String[] tuple : envTuples) {
      String envAk = emptyToNull(env.get(tuple[0]));
      String envSk = emptyToNull(env.get(tuple[1]));
      if (envAk != null && envSk != null) {
        return new Credentials(envAk, envSk, emptyToNull(env.get(tuple[2])));
      }
    }

    throw new InvalidInputException(
        "No credentials found: set "
            + SigV4Signer.PROPERTY_ACCESS_KEY_ID
            + "/"
            + SigV4Signer.PROPERTY_SECRET_ACCESS_KEY
            + " properties, "
            + "or ALIBABA_CLOUD_ACCESS_KEY_ID/ALIBABA_CLOUD_ACCESS_KEY_SECRET, "
            + "or AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY "
            + "environment variables");
  }

  private static String emptyToNull(String value) {
    return (value == null || value.isEmpty()) ? null : value;
  }
}
