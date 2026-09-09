#!/bin/sh
set -eu

repo_root=$(git rev-parse --show-toplevel)
hooks_dir=$(git rev-parse --git-path hooks)
case "$hooks_dir" in
  /*) ;;
  *) hooks_dir="$repo_root/$hooks_dir" ;;
esac
mkdir -p "$hooks_dir"

conflicts=""

install_hook() {
  name=$1
  source_hook="$repo_root/scripts/hooks/$name"
  target_hook="$hooks_dir/$name"

  if [ ! -e "$target_hook" ] && [ ! -L "$target_hook" ]; then
    install -m 0755 "$source_hook" "$target_hook"
    printf '%s\n' "Installed $target_hook"
    return
  fi

  if [ -f "$target_hook" ] && grep -q '^# osstables-secret-hook$' "$target_hook"; then
    if cmp -s "$source_hook" "$target_hook"; then
      chmod 0755 "$target_hook"
      printf '%s\n' "Already installed: $target_hook"
    else
      install -m 0755 "$source_hook" "$target_hook"
      printf '%s\n' "Updated $target_hook"
    fi
    return
  fi

  if [ "$name" = "pre-commit" ] && [ -L "$target_hook" ] &&
      [ "$(readlink "$target_hook")" = "../../scripts/check-secrets.sh" ]; then
    unlink "$target_hook"
    install -m 0755 "$source_hook" "$target_hook"
    printf '%s\n' "Migrated legacy $target_hook"
    return
  fi

  conflicts="$conflicts $name"
  printf '%s\n' "Existing $target_hook was not modified." >&2
}

install_hook pre-commit
install_hook pre-push

if [ -n "$conflicts" ]; then
  printf '%s\n' "Integrate the existing hook(s) manually; do not replace them." >&2
  for name in $conflicts; do
    if [ "$name" = "pre-commit" ]; then
      printf '%s\n' "pre-commit: add this before the existing hook logic:" >&2
      printf '%s\n' '  "$(git rev-parse --show-toplevel)/scripts/hooks/pre-commit" "$@" || exit $?' >&2
    else
      printf '%s\n' "pre-push: if the existing hook does not read stdin, add this before its logic:" >&2
      printf '%s\n' '  "$(git rev-parse --show-toplevel)/scripts/hooks/pre-push" "$@" || exit $?' >&2
      printf '%s\n' "If it reads stdin, move its current implementation to pre-push.local and use this dispatcher:" >&2
      printf '%s\n' '  input=$(mktemp) || exit 1' >&2
      printf '%s\n' '  trap '\''rm -f "$input"'\'' EXIT' >&2
      printf '%s\n' '  cat >"$input"' >&2
      printf '%s\n' '  repo_root=$(git rev-parse --show-toplevel)' >&2
      printf '%s\n' '  hooks_dir=$(git rev-parse --git-path hooks)' >&2
      printf '%s\n' '  "$repo_root/scripts/hooks/pre-push" "$@" <"$input" || exit $?' >&2
      printf '%s\n' '  "$hooks_dir/pre-push.local" "$@" <"$input" || exit $?' >&2
    fi
  done
  exit 1
fi
