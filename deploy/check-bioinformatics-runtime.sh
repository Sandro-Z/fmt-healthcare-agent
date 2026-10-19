#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
FMT_ROOT="${FMT_ROOT:-${WGS_FMT_RESOURCE_ROOT:-$APP_ROOT/var}}"
MODEL_ROOT="${WGS_FMT_TRIPLET_MODEL_DIR:-$FMT_ROOT/models/fmt-triplet-v1}"
BASELINE_SPECIES="${WGS_FMT_BASELINE_SPECIES:-$FMT_ROOT/data/fmt-matching/species_abundance_train.csv}"
MATCH_FILE="${WGS_FMT_MATCH_FILE:-$FMT_ROOT/data/fmt-matching/match.xlsx}"
if [[ ! -d "$MODEL_ROOT" && -d "$APP_ROOT/data/model-training/fmt-triplet-v1" ]]; then
    MODEL_ROOT="$APP_ROOT/data/model-training/fmt-triplet-v1"
fi
if [[ ! -s "$BASELINE_SPECIES" && -s "$FMT_ROOT/species_abundance_train.csv" ]]; then
    BASELINE_SPECIES="$FMT_ROOT/species_abundance_train.csv"
fi
if [[ ! -s "$MATCH_FILE" && -s "$FMT_ROOT/match.xlsx" ]]; then
    MATCH_FILE="$FMT_ROOT/match.xlsx"
fi
ALLOW_MISSING_DATABASES=false
if [[ "${1:-}" == "--allow-missing-databases" ]]; then
    ALLOW_MISSING_DATABASES=true
fi

missing=0
check_path() {
    local path="$1"
    local type="${2:-file}"
    if [[ "$type" == executable && ! -x "$path" ]]; then
        printf 'MISSING executable %s\n' "$path" >&2
        missing=$((missing + 1))
    elif [[ "$type" == directory && ! -d "$path" ]]; then
        printf 'MISSING directory  %s\n' "$path" >&2
        missing=$((missing + 1))
    elif [[ "$type" == file && ! -s "$path" ]]; then
        printf 'MISSING file       %s\n' "$path" >&2
        missing=$((missing + 1))
    else
        printf 'OK      %s\n' "$path"
    fi
}

check_path "$APP_ROOT/runtime/scripts/postfmt_pipeline/process_postfmt_sample.sh" executable
check_path "$FMT_ROOT/runtime/envs/fmt-tax/bin/fastp" executable
check_path "$FMT_ROOT/runtime/envs/fmt-tax/bin/kneaddata" executable
check_path "$FMT_ROOT/runtime/envs/fmt-tax/bin/metaphlan" executable
check_path "$FMT_ROOT/runtime/envs/fmt-tax/bin/pigz" executable
check_path "$FMT_ROOT/runtime/envs/fmt-func/bin/humann" executable
check_path "$FMT_ROOT/runtime/envs/fmt-func/bin/humann_renorm_table" executable

if [[ "$ALLOW_MISSING_DATABASES" != true ]]; then
    check_path "$FMT_ROOT/databases/kneaddata/hg_39/hg_39.1.bt2"
    check_path "$FMT_ROOT/databases/metaphlan4/mpa_vJan25_CHOCOPhlAnSGB_202503.pkl"
    check_path "$FMT_ROOT/databases/metaphlan4_vJun23/mpa_vJun23_CHOCOPhlAnSGB_202307.pkl"
    check_path "$FMT_ROOT/databases/humann3/chocophlan" directory
    check_path "$FMT_ROOT/databases/humann3/uniref/uniref90_201901b_full.dmnd"
    check_path "$FMT_ROOT/databases/humann3/utility_mapping/map_ko_uniref90.txt.gz"
    check_path "$MODEL_ROOT/feature_schema.json"
    check_path "$MODEL_ROOT/fmt_triplet_contrastive_model.npz"
    check_path "$BASELINE_SPECIES"
    check_path "$MATCH_FILE"
fi

if (( missing > 0 )); then
    printf '\nRuntime check failed: %d required path(s) missing.\n' "$missing" >&2
    exit 1
fi
printf '\nRuntime check passed for FMT_ROOT=%s\n' "$FMT_ROOT"
