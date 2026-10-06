#!/usr/bin/env bash
# Print per-worktree environment values (offset, ports, names).
# Usage: scripts/resolve-env.sh [--export]
# A preset APP_OFFSET (integer 0-99) overrides the derivation.
set -euo pipefail

prefix=""
case "${1:-}" in
  "") ;;
  --export) prefix="export " ;;
  *)
    echo "Usage: resolve-env.sh [--export]" >&2
    exit 2
    ;;
esac

if [[ -n "${APP_OFFSET+x}" ]]; then
  if ! [[ "$APP_OFFSET" =~ ^[0-9]{1,2}$ ]]; then
    echo "APP_OFFSET must be an integer from 0 to 99" >&2
    exit 1
  fi
  offset=$((10#$APP_OFFSET))
else
  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "resolve-env.sh must run inside a git work tree" >&2
    exit 1
  fi
  git_dir=$(git rev-parse --path-format=absolute --git-dir)
  common_dir=$(git rev-parse --path-format=absolute --git-common-dir)
  if [[ "$git_dir" == "$common_dir" ]]; then
    offset=0
  else
    top=$(git rev-parse --show-toplevel)
    sum=$(printf '%s' "$top" | cksum | cut -d' ' -f1)
    offset=$((sum % 99 + 1))
  fi
fi

if [[ "$offset" -eq 0 ]]; then
  name="bugflow"
else
  name="bugflow_w${offset}"
fi

printf '%sAPP_OFFSET=%s\n' "$prefix" "$offset"
printf '%sPOSTGRES_PORT=%s\n' "$prefix" $((5432 + offset))
printf '%sPOSTGRES_DB=%s\n' "$prefix" "$name"
printf '%sCOMPOSE_PROJECT_NAME=%s\n' "$prefix" "$name"
printf '%sAPI_PORT=%s\n' "$prefix" $((8000 + offset))
printf '%sFRONTEND_PORT=%s\n' "$prefix" $((3000 + offset))
