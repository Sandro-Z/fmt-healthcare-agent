#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
FMT_ROOT="${FMT_ROOT:-${WGS_FMT_RESOURCE_ROOT:-$APP_ROOT/var}}"
ENV_ROOT="${ENV_ROOT:-$FMT_ROOT/runtime/envs}"

if command -v micromamba >/dev/null 2>&1; then
    ENV_CREATE=(micromamba create --yes --prefix)
elif command -v mamba >/dev/null 2>&1; then
    ENV_CREATE=(mamba env create --yes --prefix)
elif command -v conda >/dev/null 2>&1; then
    ENV_CREATE=(conda env create --yes --prefix)
else
    printf 'Install micromamba, mamba, or conda first.\n' >&2
    exit 2
fi

mkdir -p "$ENV_ROOT"
for environment in fmt-tax fmt-func; do
    target="$ENV_ROOT/$environment"
    definition="$APP_ROOT/runtime/environments/$environment.yml"
    if [[ -x "$target/bin/python" ]]; then
        printf 'SKIP existing environment: %s\n' "$target"
        continue
    fi
    printf 'CREATE %s from %s\n' "$target" "$definition"
    "${ENV_CREATE[@]}" "$target" --file "$definition"
done

FMT_ROOT="$FMT_ROOT" "$SCRIPT_DIR/check-bioinformatics-runtime.sh" --allow-missing-databases
