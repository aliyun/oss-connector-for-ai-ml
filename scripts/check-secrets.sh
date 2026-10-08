#!/bin/sh
set -eu

usage() {
  printf '%s\n' "usage: $0 [staged | range <git-log-options>]" >&2
  exit 2
}

repo_root=$(git rev-parse --show-toplevel)
config="$repo_root/.gitleaks.toml"

if command -v gitleaks >/dev/null 2>&1; then
  gitleaks_bin=$(command -v gitleaks)
elif [ -x "$HOME/.local/bin/gitleaks" ]; then
  gitleaks_bin="$HOME/.local/bin/gitleaks"
else
  printf '%s\n' "gitleaks is required: install it and retry" >&2
  exit 1
fi

mode=${1:-staged}
case "$mode" in
  staged)
    [ "$#" -le 1 ] || usage
    exec "$gitleaks_bin" git \
      --pre-commit \
      --staged \
      --config "$config" \
      --redact=100 \
      --no-banner \
      "$repo_root"
    ;;
  range)
    [ "$#" -eq 2 ] || usage
    [ -n "$2" ] || usage
    exec "$gitleaks_bin" git \
      --log-opts="$2" \
      --config "$config" \
      --redact=100 \
      --no-banner \
      "$repo_root"
    ;;
  *)
    usage
    ;;
esac
