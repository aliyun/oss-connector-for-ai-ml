package com.aliyun.osstables.lance;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.lance.namespace.client.apache.ApiException;
import org.lance.namespace.errors.ErrorFactory;
import org.lance.namespace.errors.InternalException;
import org.lance.namespace.errors.InvalidInputException;
import org.lance.namespace.errors.LanceNamespaceException;
import org.lance.namespace.errors.PermissionDeniedException;
import org.lance.namespace.errors.ServiceUnavailableException;
import org.lance.namespace.errors.ThrottlingException;
import org.lance.namespace.errors.UnauthenticatedException;

/**
 * Translates a generated-client {@link ApiException} into the appropriate {@link
 * LanceNamespaceException}. Ports {@code _to_namespace_error}: an integer {@code code} in the JSON
 * body takes precedence (mapped via {@link ErrorFactory#fromErrorCode}); otherwise the HTTP status
 * is mapped, defaulting to {@link InternalException}.
 */
final class ErrorTranslator {

  private static final ObjectMapper MAPPER = new ObjectMapper();

  private ErrorTranslator() {}

  /** A generated-client call that may throw {@link ApiException}. */
  interface Call<T> {
    T run() throws ApiException;
  }

  /** A generated-client call with no return value that may throw {@link ApiException}. */
  interface VoidCall {
    void run() throws ApiException;
  }

  static <T> T translate(Call<T> call) {
    try {
      return call.run();
    } catch (ApiException e) {
      throw toException(e);
    }
  }

  static void translateVoid(VoidCall call) {
    try {
      call.run();
    } catch (ApiException e) {
      throw toException(e);
    }
  }

  static LanceNamespaceException toException(ApiException e) {
    Integer code = null;
    String message = null;
    String body = e.getResponseBody();
    if (body != null && !body.isEmpty()) {
      try {
        JsonNode node = MAPPER.readTree(body);
        JsonNode codeNode = node.get("code");
        if (codeNode != null && codeNode.canConvertToInt()) {
          code = codeNode.asInt();
        }
        JsonNode error = node.get("error");
        JsonNode detail = node.get("detail");
        if (error != null && !error.isNull()) {
          message = error.asText();
        } else if (detail != null && !detail.isNull()) {
          message = detail.asText();
        }
      } catch (Exception ignored) {
        // fall through to the HTTP-status message below
      }
    }
    if (message == null) {
      message = "HTTP " + e.getCode() + ": " + (body != null && !body.isEmpty() ? body : "");
    }
    if (code != null) {
      return ErrorFactory.fromErrorCode(code, message);
    }
    switch (e.getCode()) {
      case 400:
        return new InvalidInputException(message);
      case 401:
        return new UnauthenticatedException(message);
      case 403:
        return new PermissionDeniedException(message);
      case 429:
        return new ThrottlingException(message);
      case 503:
        return new ServiceUnavailableException(message);
      default:
        return new InternalException(message);
    }
  }
}
