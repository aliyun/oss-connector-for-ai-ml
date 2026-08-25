package com.aliyun.lance.osstables;

/**
 * Provider of environment-variable values, injectable so credential resolution can be unit-tested.
 *
 * <p>Java cannot mutate {@link System#getenv()}, so tests pass a map-backed implementation instead.
 */
public interface EnvProvider {

  /** @return the value of environment variable {@code name}, or {@code null} if unset. */
  String get(String name);

  /** @return an {@link EnvProvider} backed by the real process environment. */
  static EnvProvider system() {
    return System::getenv;
  }
}
